# Research Service

FastAPI service that retrieves medical research evidence from PubMed and caches
results for faster repeat queries.

## What it does

- Searches PubMed for a query.
- Normalizes and ranks results by relevance.
- Caches responses to reduce repeated lookups.

## Endpoints

- `GET /health` returns cache status.
- `POST /research` searches research sources for a query.

## Environment

- `REDIS_URL` (required) — Redis connection for distributed PubMed rate limiting.
- `PUBMED_API_KEY` (optional) — PubMed API key.
- `PUBMED_MAX_RPS` (optional, default `8`) — max PubMed requests/sec shared across all instances.

## Example curls

```bash
curl -s http://localhost:8003/health
```

```bash
curl -s http://localhost:8003/research \
	-H "Content-Type: application/json" \
	-d '{
		"query": "creatine muscle performance",
		"max_results": 5,
		"sources": ["pubmed"]
	}'
```
