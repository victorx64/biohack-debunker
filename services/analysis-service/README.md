# Analysis Service

FastAPI service that extracts claims from transcripts, fetches supporting evidence,
and uses an LLM to produce an analysis summary.

## What it does

- Extracts key claims from a transcript.
- Queries the research service for evidence per claim.
- Produces verdicts, confidence scores, and a report summary.

## Endpoints

- `GET /health` returns service status and LLM configuration.
- `POST /analyze` analyzes a transcript and returns claim-level results.

## Example curls

```bash
curl -s http://localhost:8002/health
```

```bash
curl -s http://localhost:8002/analyze \
	-H "Content-Type: application/json" \
	-d '{
		"segments": [
			{
				"start": 0.0,
				"end": 8.0,
				"text": "Omega-3 supplementation reduces triglycerides and may improve cardiovascular outcomes."
			}
		],
		"claims_per_chunk": 3,
		"research_max_results": 3,
		"research_sources": ["pubmed"]
	}'
```
