# DeepEval analysis tests

These tests call the analysis service, match extracted claims to expected claims, and run DeepEval metrics.
They also produce an aggregate stakeholder report with claim extraction and veracity classification metrics.

## Stakeholder metrics report

At the end of a run, tests now save a JSON report (`metrics_summary.json`) with:

- Claim extraction metrics (presence/absence level):
  - `precision`, `recall`, `f1`
  - based on `TP=matched`, `FN=missing expected`, `FP=extra extracted`
- Veracity/status metrics on matched claims:
  - `accuracy`
  - `macro_f1`, `weighted_f1`
  - per-class `precision/recall/f1/support`
  - full `confusion_matrix`
  - critical flips: `supported_to_refuted` and `refuted_to_supported`

By default the report is written to:

- `services/analysis-service/tests/deepeval/outputs/metrics_summary.json`

The test logs also print a one-line aggregate summary with extraction F1, veracity accuracy, and macro F1.

## Service goal and test intent

The analysis service is designed to retrieve and reason over **strong human evidence** for medical claims.
In practice, PubMed retrieval is intentionally biased toward higher-evidence publication types (for example,
meta-analyses, systematic reviews, randomized clinical trials, and clinical trials), plus human-focused indexing.

Because of that, the DeepEval dataset should mainly test claims that are realistically answerable from this evidence profile.

### What claims we should test

- Claims that are medically verifiable in humans (causal or outcome-oriented statements).
- Claims with clear clinical concepts (population/intervention/exposure/outcome) that map to PubMed terms.
- Claims where high-quality human literature is expected to exist (or is known to exist).
- Controversial or high-impact claims are preferred over generic wellness statements.

### What claims to avoid in the main dataset

- Claims that rely on vague phrasing with poor PubMed term mapping.
- Claims that are unlikely to have strong human evidence and will systematically return zero sources.
- Claims better suited to animal/mechanistic evidence when the test expects a supported/refuted verdict from human studies.

If a case repeatedly returns no eligible human evidence due to claim wording (not because the topic lacks literature),
update the test claim phrasing to better align with searchable biomedical terminology.

### Claim wording checklist (to avoid false `not_assessable`)

- Prefer canonical clinical terms over conversational modifiers (for example, use `MMR vaccine` instead of `routine childhood vaccines` when the topic is MMR).
- Avoid over-constraining words that are often not indexed in titles/abstracts (for example, `consistent`, `regular use`, `sustained`, `uncomplicated`) unless essential.
- Keep the claim atomic and short, with one intervention/exposure and one outcome.
- Include the core human context only when useful (`adults`, `children`, `humans`) but avoid stacking extra qualifiers in one sentence.
- For infection-treatment claims, use disease names commonly represented in trials/reviews (for example, `common cold`, `URTI`) rather than long colloquial phrases.
- If a case returns `not_assessable` with zero sources, first rephrase the claim; only then reconsider the expected verdict.

## Dataset format

File: services/analysis-service/tests/deepeval/fixtures/analysis_dataset.json

```json
[
  {
    "id": "case-001",
    "segments": [
      {"start": 0.0, "end": 8.0, "text": "..."}
    ],
    "analysis_params": {
      "claims_per_chunk": 2,
      "chunk_size_chars": 2000,
      "research_max_results": 3,
      "research_sources": ["pubmed"]
    },
    "expected_claims": [
      {
        "claim": "...",
        "verdict": "supported",
        "verdict_any_of": ["supported", "likely_supported"],
        "references": [
          {
            "title": "Source title",
            "url": "https://..."
          }
        ]
      }
    ]
  }
]
```

Notes:
- Use either `verdict` or `verdict_any_of` per claim.
- `verdict_any_of` helps with minor label variations.
- `references` is optional metadata for stakeholder traceability and is not used by test assertions.
- Canonical verdicts: `supported`, `likely_supported`, `conflicting`, `insufficient_evidence`, `likely_refuted`, `refuted`, `not_assessable`.

## Environment variables

- `ANALYSIS_BASE_URL` (default: http://analysis-service:8002)
- `DEEPEVAL_DATASET_PATH` (default: fixtures/analysis_dataset.json)
- `DEEPEVAL_MODEL` (default: gpt-4o-mini)
- `DEEPEVAL_VERDICT_THRESHOLD` (default: 0.8)
- `DEEPEVAL_FAITHFULNESS_THRESHOLD` (default: 0.5)
- `DEEPEVAL_CLAIM_MATCH_THRESHOLD` (default: 0.6)
- `DEEPEVAL_CLAIM_MATCH_MODE` (default: `entailment`; supported: `entailment`/`hybrid`/`similarity`)
- `DEEPEVAL_CLAIM_MATCH_EQUIVALENCE` (default: `false`; when `true`, requires bidirectional entailment)
- `DEEPEVAL_ENTAILMENT_TIMEOUT` (default: `20`; seconds for one entailment judge request)
- `DEEPEVAL_MAX_CLAIMS_PER_CASE` (default: 10)
- `DEEPEVAL_CASE_IDS` (optional: comma-separated case IDs to run, e.g. `case-001,case-003`)
- `DEEPEVAL_RESEARCH_MAX_RESULTS_OVERRIDE` (optional: force `research_max_results` for all cases)
- `DEEPEVAL_OUTPUT_DIR` (optional but recommended: directory to save raw analysis-service responses for debugging)
- `DEEPEVAL_METRICS_REPORT_PATH` (optional: explicit path for aggregate `metrics_summary.json`; if omitted, uses `DEEPEVAL_OUTPUT_DIR/metrics_summary.json` when `DEEPEVAL_OUTPUT_DIR` is set, otherwise `outputs/metrics_summary.json`)
- `DEEPEVAL_PYTEST_WORKERS` (default: `auto`; used by `pytest -n` in `docker-compose.deepeval.yml`)
- `DEEPEVAL_RUN_ID` (optional: shared run ID for worker-safe metrics merge; auto-generated in compose command)

## Docker compose

The `deepeval-analysis` service in docker-compose.deepeval.yml runs these tests against the analysis service
from the base docker-compose.yml. Make sure your .env provides LLM credentials for both the analysis
service and DeepEval.

### Rebuild requirement after service code changes

If you changed service code (for example in `analysis-service`, `research-service`, `api-gateway`, or shared code used by them),
rebuild compose services before running DeepEval tests:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml build analysis-service deepeval-analysis
```

`deepeval-analysis` now runs with pytest-xdist (`pytest -n ...`) and merges per-case metrics into one final
`metrics_summary.json` at session end.

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm deepeval-analysis
```

Limit parallelism (example: 4 workers):

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_PYTEST_WORKERS=4 \
  deepeval-analysis
```

Run a single case:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_CASE_IDS=case-002 \
  deepeval-analysis
```

Run a single case and always save raw responses (recommended for debugging):

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_CASE_IDS=case-002 \
  -e DEEPEVAL_OUTPUT_DIR=/app/services/analysis-service/tests/deepeval/outputs \
  deepeval-analysis
```

After the run, inspect saved JSON files in `services/analysis-service/tests/deepeval/outputs/`.
The aggregate report will be available as `metrics_summary.json` in the same directory (unless `DEEPEVAL_METRICS_REPORT_PATH` is set).

You can pass multiple case IDs as a comma-separated list:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_CASE_IDS=case-001,case-003 \
  deepeval-analysis
```

Fast smoke run example:

```bash
DEEPEVAL_CASE_IDS=case-001 DEEPEVAL_RESEARCH_MAX_RESULTS_OVERRIDE=5 \
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm deepeval-analysis
```

Save aggregate report to a custom location:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_METRICS_REPORT_PATH=/app/services/analysis-service/tests/deepeval/outputs/stakeholder-metrics.json \
  deepeval-analysis
```
