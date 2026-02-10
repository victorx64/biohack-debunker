# API Gateway

FastAPI gateway that orchestrates transcription and analysis services, storing
results in PostgreSQL and enforcing rate limits via Redis.

## Environment

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL` (optional override)
- `REDIS_URL`
- `TRANSCRIPTION_SERVICE_URL`
- `ANALYSIS_SERVICE_URL`
- `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`
- `ENABLE_PUBLIC_FEED`, `ENABLE_BILLING`, `FREE_TIER_CREDITS`

## Run

```bash
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000
```
