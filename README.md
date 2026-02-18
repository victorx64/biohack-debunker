# BioHack Debunker

**Production-style AI engineering showcase**: a platform that ingests YouTube videos, extracts medical claims, retrieves PubMed evidence, and returns structured verdicts with explanations, confidence, and citations.

This repository is built as an **end-to-end system for AI engineering**: microservices, orchestration, retrieval + reasoning, quality gates, observability, cost tracking, fallback policy, and reproducible testing.

---

## TL;DR

- Built a **RAG-like veracity pipeline** (not pure generation): transcript → claims → research evidence → adjudication → report.
- Implemented **service decomposition**: `api-gateway`, `analysis-service`, `research-service`, `transcription-service`, dedicated worker, PostgreSQL, Redis, optional Qdrant.
- Added **measurable quality evaluation** with DeepEval + aggregate stakeholder report (`precision/recall/F1`, `accuracy`, `macro-F1`, confusion matrix).
- Added **observability baseline**: cross-service correlation/request IDs, structured JSON logs, Prometheus metrics, Grafana dashboard.
- Added **stage-based model routing + fallback policy** (`extraction`, `adjudication`, `report`) with retry/backoff, fallback budget, and quality/latency/cost guardrails.
- Included **cost/usage accounting in the data model** (prompt/completion tokens, PubMed calls) for practical optimization work.

---

## Problem and product value

Medical misinformation spreads faster than manual fact-checking can scale.

BioHack Debunker automates this workflow:

1. Extract transcript from YouTube.
2. Identify medically testable claims.
3. Query PubMed for supporting/contradicting evidence.
4. Produce claim-level verdicts.
5. Return structured results with explanation and sources.

---

## Architecture (microservices + async orchestration)

```text
Frontend (Streamlit)
        |
        v
API Gateway (FastAPI, :8000)
  - Rate limiting (Redis)
  - Persistence (PostgreSQL)
  - Request routing
  - Async enqueue
        |
        +--> Analysis Worker (queue consumer + retries + DLQ)
        |
        +--> Transcription Service (:8001, yt-dlp)
        |
        +--> Analysis Service (:8002, LLM pipeline)
                    |
                    +--> Research Service (:8003, PubMed + cache + throttling)

Infra/data: PostgreSQL 16 + Redis 7 + optional Qdrant
```

### Core engineering decisions

- **Gateway + worker split**: API remains responsive while long-running analysis executes asynchronously.
- **Retry/DLQ path**: controlled retries and dead-letter handling for robustness.
- **Shared contracts** via common package `shared/` and Pydantic schemas.
- **Migrations-first data evolution** through Alembic (`migrations/versions/`).
- **Config-driven runtime**: behavior and model routing controlled by environment variables.

---

## End-to-end data flow

1. `POST /api/v1/analysis` hits the gateway.
2. Gateway applies rate-limit checks and inserts `analyses` row in PostgreSQL (`pending`).
3. Worker calls transcription service to get transcript + segments + video metadata.
4. Worker calls analysis service.
5. Analysis service:
   - extracts claims,
   - queries research service per claim,
   - computes verdict/confidence/explanation,
   - builds aggregate report.
6. Gateway persists `claims`, `sources`, and usage/cost counters.
7. Client polls `GET /api/v1/analysis/{id}` until `completed/failed`.

---

## What is measured (metrics that matter)

### 1) Extraction and verdict quality (DeepEval)

The test harness generates an aggregate stakeholder report (`metrics_summary.json`) with:

- **Extraction level**: `precision`, `recall`, `f1`
  - `TP = matched claims`, `FN = missing expected`, `FP = extra extracted`.
- **Veracity level** (on matched claims):
  - `accuracy`
  - `macro_f1`, `weighted_f1`
  - per-class `precision/recall/f1/support`
  - `confusion_matrix`
  - critical flips: `supported_to_refuted`, `refuted_to_supported`.

### 2) Runtime/operational signals

Per-service Prometheus metrics (`GET /metrics`):

- `http_requests_total{service,endpoint,method,status}`
- `http_request_duration_ms_bucket{service,endpoint,method,...}`
- `http_request_errors_total{service,endpoint,method,status}`
- `llm_tokens_total{service,kind}` (gateway + analysis)
- `pubmed_calls_total{service,endpoint}` (gateway + analysis + research)

`http_request_duration_ms_bucket` is used for p50/p95 latency calculations.

### 3) Data-model cost accounting

`analyses` and `claims` include counters for engineering economics:

- LLM prompt/completion tokens
- total PubMed requests
- report-stage token split

This enables cost-per-analysis tracking, stage-level optimization, and regression detection.

---

## Observability baseline (implemented)

Traceability is propagated across services with:

- `X-Request-ID`
- `X-Correlation-ID`
- `X-Analysis-ID` (when available)

Structured JSON logs include:

- `service`, `endpoint`, `duration_ms`, `status`
- `analysis_id`, `request_id`, `correlation_id`

Benefits:

- Faster cross-service root-cause analysis.
- Unified context for latency/error/usage investigation.

---

## Model routing + fallback policy (production-minded MVP)

LLM stages are explicitly separated:

- `extraction`
- `adjudication`
- `report`

### Routing strategy

- `extraction`: low-latency/lower-cost primary + fallback.
- `adjudication`: quality-first primary + balanced fallback.
- `report`: same family as adjudication for consistency + fallback.

### Fallback trigger conditions

- HTTP: `429`, `500`, `502`, `503`, `504`
- request/read timeout
- empty content
- invalid JSON / schema parse failure (after retries)

### Resilience defaults

- `per-model retries = 1`
- exponential backoff: `0.3s` → `0.9s`
- `max fallbacks per stage = 2`

### Guardrails (quality + economics)

- Extraction: `F1 >= 0.70`
- Veracity: `accuracy >= 0.75`
- Veracity: `macro-F1 >= 0.65`
- p95 latency drift: `<= 25%` vs baseline
- LLM cost drift: `<= 20%` vs baseline

---

## API surface

- `POST /api/v1/analysis` — create analysis request from a YouTube URL
- `GET /api/v1/analysis/{id}` — fetch status/result
- `GET /api/v1/feed` — public feed of completed analyses (when enabled)
- `GET /health` — health checks
- `GET /metrics` — Prometheus metrics endpoint (per service)

---

## Tech stack

- **Language/runtime:** Python 3.12
- **Backend:** FastAPI, Pydantic, httpx, async service calls
- **AI layer:** OpenAI-compatible Chat Completions (provider/model configurable)
- **Data:** PostgreSQL 16, Redis 7
- **Evidence retrieval:** PubMed E-utilities
- **Infra:** Docker + Docker Compose (+ overlays)
- **Migrations:** Alembic
- **Testing:** Pytest (unit/integration) + DeepEval
- **Observability:** Prometheus + Grafana + structured logs

---

## Repository layout

```text
.
├── services/
│   ├── api-gateway/
│   ├── transcription-service/
│   ├── analysis-service/
│   └── research-service/
├── migrations/
├── shared/
├── frontend/
├── observability/
├── docker-compose.yml
├── docker-compose.integration.yml
├── docker-compose.deepeval.yml
└── docker-compose.observability.yml
```

---

## Quick start (local)

### 1) Configure `.env`

```bash
cp .env.example .env
```

Required minimum:

- `OPENAI_API_KEY`
- `LLM_PROVIDER` (for example: `openai`)
- `LLM_MODEL` (for example: `gpt-4o-mini`)

Recommended:

- `PUBMED_API_KEY` (higher PubMed throughput)

### 2) Start all services

```bash
make up
```

### 3) Verify gateway health

```bash
curl -sS http://localhost:8000/health
```

### 4) Submit an analysis request

```bash
curl -sS -X POST "http://localhost:8000/api/v1/analysis" \
  -H "Content-Type: application/json" \
  -H "x-user-email: demo@example.com" \
  -d '{"youtube_url":"https://www.youtube.com/watch?v=ITyg5EdfX3o","is_public":true,"research_sources":["pubmed"]}'
```

### 5) Open UI

- Streamlit frontend: http://localhost:8501

---

## Runbooks: testing and quality checks

### Integration suites (service-level)

```bash
make test-integration
```

Targeted suites:

```bash
make test-integration-gateway
make test-integration-analysis
make test-integration-research
make test-integration-transcription
```

Strict mode for real external dependencies:

```bash
ANALYSIS_REQUIRE_LLM=1 make test-integration-analysis
RESEARCH_REQUIRE_REAL=1 make test-integration-research
```

### DeepEval quality suite

```bash
make test-deepeval
```

Run a single case:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_CASE_IDS=case-021 \
  deepeval-analysis
```

Save raw outputs:

```bash
docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm \
  -e DEEPEVAL_CASE_IDS=case-021 \
  -e DEEPEVAL_OUTPUT_DIR=/app/services/analysis-service/tests/deepeval/outputs \
  deepeval-analysis
```

Metrics artifact path: `services/analysis-service/tests/deepeval/outputs/metrics_summary.json`

---

## Observability stack (Prometheus + Grafana)

Start with observability overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
```

Endpoints:

- Prometheus: http://localhost:9090
- Targets: http://localhost:9090/targets
- Grafana: http://localhost:3000 (`admin/admin`)
- Dashboard: `BioHack / BioHack Observability`

Useful PromQL examples:

```promql
# p95 latency by service
histogram_quantile(0.95, sum by (le, service) (rate(http_request_duration_ms_bucket[5m])))

# error rate by service
sum(rate(http_request_errors_total[5m])) by (service)
/
sum(rate(http_requests_total[5m])) by (service)

# throughput by service
sum(rate(http_requests_total[1m])) by (service)
```

---

## Stage-level LLM routing env (example)

Global:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_MAX_RETRIES`
- `LLM_RETRY_BACKOFF`
- `LLM_MAX_FALLBACKS`

Stage overrides:

- `LLM_MODEL_EXTRACTION`
- `LLM_MODEL_EXTRACTION_FALLBACKS`
- `LLM_MODEL_ADJUDICATION`
- `LLM_MODEL_ADJUDICATION_FALLBACKS`
- `LLM_MODEL_REPORT`
- `LLM_MODEL_REPORT_FALLBACKS`

---

## Why this is a strong AI engineering project

- It is not a toy demo: it is a **multi-service production-style system** with orchestration and persistence.
- Quality is **measured quantitatively**, not described subjectively.
- Observability is implemented as an **engineering baseline** (IDs, logs, metrics, dashboards).
- The schema supports **cost-aware optimization** across latency/cost/quality trade-offs.
- LLM calls use **resilience policy with explicit guardrails**.

---

## Next upgrades

- Add OpenTelemetry traces with full distributed tracing backend.
- Implement robust evidence cache invalidation + warmup strategy.
- Add human-in-the-loop review workflow for borderline claims.
- Add automated benchmark reports for baseline vs routing-policy variants.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).