# DeepEval analysis tests

These tests call the analysis service, match extracted claims to expected claims, and run DeepEval metrics.

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
- `DEEPEVAL_MAX_CLAIMS_PER_CASE` (default: 10)
- `DEEPEVAL_CASE_IDS` (optional: comma-separated case IDs to run, e.g. `case-001,case-003`)
- `DEEPEVAL_RESEARCH_MAX_RESULTS_OVERRIDE` (optional: force `research_max_results` for all cases)
- `DEEPEVAL_OUTPUT_DIR` (optional but recommended: directory to save raw analysis-service responses for debugging)

## Docker compose

The `deepeval-analysis` service in docker-compose.deepeval.yml runs these tests against the analysis service
from the base docker-compose.yml. Make sure your .env provides LLM credentials for both the analysis
service and DeepEval.

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm deepeval-analysis
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
