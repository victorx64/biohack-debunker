# API Gateway

FastAPI gateway that orchestrates transcription and analysis services, storing
results in PostgreSQL and enforcing rate limits via Redis.

## Environment

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL` (optional override)
- `REDIS_URL`
- `TRANSCRIPTION_SERVICE_URL`
- `ANALYSIS_SERVICE_URL`
- `ANALYSIS_QUEUE_NAME`, `ANALYSIS_DLQ_NAME`
- `ANALYSIS_MAX_RETRIES`, `ANALYSIS_RETRY_BACKOFF_SECONDS`, `ANALYSIS_WORKER_POLL_TIMEOUT`
- `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`
- `ENABLE_PUBLIC_FEED`, `ENABLE_BILLING`, `FREE_TIER_CREDITS`

## Run

```bash
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000
```

Run worker:

```bash
python3 -m api_gateway.worker
```

## Integration tests

Run gateway integration tests via Docker Compose service:

```bash
docker compose -f docker-compose.yml -f docker-compose.integration.yml run --rm --build itest-api-gateway
```

Optional environment overrides:

- `GATEWAY_BASE_URL` (default `http://api-gateway:8000`)
- `GATEWAY_TEST_USER_EMAIL` (default `integration@test.local`)
- `GATEWAY_POLL_TIMEOUT_S` (default `180`)

## Curl examples

```bash
BASE_URL=http://localhost:8000
```

Health check:

```bash
curl -sS "$BASE_URL/health"
```

Create analysis (async):

```bash
curl -sS -X POST "$BASE_URL/api/v1/analysis" \
	-H "Content-Type: application/json" \
	-H "x-user-email: demo@example.com" \
	-d '{"youtube_url":"https://www.youtube.com/watch?v=ITyg5EdfX3o","is_public":true,"research_sources":["pubmed"]}'

# Force new analysis even if this video was already analyzed:
curl -sS -X POST "$BASE_URL/api/v1/analysis" \
	-H "Content-Type: application/json" \
	-H "x-user-email: demo@example.com" \
	-d '{"youtube_url":"https://www.youtube.com/watch?v=ITyg5EdfX3o","force":true,"is_public":true}'
```

Poll analysis status (replace ANALYSIS_ID):

```bash
curl -sS "$BASE_URL/api/v1/analysis/ANALYSIS_ID"
```

Public feed (when enabled):

```bash
curl -sS "$BASE_URL/api/v1/feed?page=1&limit=20"
```
