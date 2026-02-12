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
        "verdict_any_of": ["supported", "mostly supported"]
      }
    ]
  }
]
```

Notes:
- Use either `verdict` or `verdict_any_of` per claim.
- `verdict_any_of` helps with minor label variations.

## Environment variables

- `ANALYSIS_BASE_URL` (default: http://analysis-service:8002)
- `DEEPEVAL_DATASET_PATH` (default: fixtures/analysis_dataset.json)
- `DEEPEVAL_MODEL` (default: gpt-4o-mini)
- `DEEPEVAL_VERDICT_THRESHOLD` (default: 0.8)
- `DEEPEVAL_FAITHFULNESS_THRESHOLD` (default: 0.5)
- `DEEPEVAL_CLAIM_MATCH_THRESHOLD` (default: 0.6)
- `DEEPEVAL_MAX_CLAIMS_PER_CASE` (default: 10)
- `DEEPEVAL_OUTPUT_DIR` (optional: directory to save raw analysis-service responses)

## Docker compose

The `deepeval-analysis` service in docker-compose.deepeval.yml runs these tests against the analysis service
from the base docker-compose.yml. Make sure your .env provides LLM credentials for both the analysis
service and DeepEval.

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm deepeval-analysis
```
