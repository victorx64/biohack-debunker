# BioHack Debunker - AI-Powered Health Claims Analyzer

Analyze YouTube videos from biohackers and health influencers. Produce evidence-based fact-checks from recent medical research.

## Project Overview

Problem: Health misinformation spreads rapidly on YouTube. Viewers lack time and expertise to verify claims against scientific literature.

Solution: An AI service that:
1. Extracts claims from YouTube subtitles
2. Cross-references them with peer-reviewed medical research
3. Provides evidence-based analysis with citations

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DOCKER COMPOSE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────────────────────────────────────┐  │
│  │              │     │              API GATEWAY (FastAPI)               │  │
│  │   Frontend   │────▶│  - Rate Limiting   - Request Routing             │  │
│  │              │     │  - Credits (mock) - Orchestration                │  │
│  │              │     │  Port 8000                                       │  │
│  └──────────────┘     └──────────┬────────────────┬───────────────┬──────┘  │
│                                  │                │               │         │
│                      ┌───────────┴────┐ ┌─────────┴────┐ ┌────────┴──────┐  │
│                      │                │ │              │ │               │  │
│                      │  Transcription │ │   Analysis   │ │   Research    │  │
│                      │    Service     │ │   Service    │ │    Service    │  │
│                      │    (Python)    │ │   (Python)   │ │   (Python)    │  │
│                      │    Port 8001   │ │   Port 8002  │ │   Port 8003   │  │
│                      │   yt-dlp       │ │   LLM calls  │ │    PubMed    │  │
│                      │                │ │              │ │  In-memory    │  │
│                      │                │ │              │ │  cache        │  │
│                      └───────┬────────┘ └──────┬───────┘ └───────┬───────┘  │
│                              │                 │                 │          │
│                              │                 │                 │          │
│  ┌───────────────────────────┴──────────────────────────────────────────┐   │
│  │                               DATA LAYER                             │   │
│  │   ┌────────────┐                           ┌────────────────────┐    │   │
│  │   │ PostgreSQL │                           │        Redis       │    │   │
│  │   │  (Main DB) │                           │ Rate limit + PubMed│    │   │
│  │   │  Port 5432 │                           │ throttling         │    │   │
│  │   └────────────┘                           └────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- The frontend folder is currently a placeholder.
- Research caching is in-memory in the research service; Redis is used for rate limiting and PubMed request throttling.

---

## Project Structure

```
biohack-debunker/
├── docker-compose.yml
├── docker-compose.prod.yml
├── docker-compose.test.yml
├── Makefile
├── ARCHITECTURE.md
│
├── frontend/                    # Placeholder for UI
│   └── README.md
│
├── services/
│   ├── api-gateway/             # FastAPI - main entry point
│   │   ├── src/api_gateway/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── routers/          # analysis, feed, health
│   │   │   ├── middleware/       # auth, rate_limit
│   │   │   └── services/         # orchestrator
│   │   └── tests/
│   │       └── integration/
│   │
│   ├── transcription-service/   # YouTube subtitles via yt-dlp
│   │   ├── src/transcription_service/
│   │   │   ├── main.py
│   │   │   ├── youtube_client.py
│   │   │   ├── transcript_parser.py
│   │   │   └── yt_dlp_runner.py
│   │   └── tests/
│   │       ├── integration/
│   │       └── unit/
│   │
│   ├── analysis-service/        # Claim extraction and analysis
│   │   ├── src/analysis_service/
│   │   │   ├── main.py
│   │   │   ├── chains/           # extract, analyze, report
│   │   │   ├── prompts/          # extraction, analysis
│   │   │   └── llm_client.py
│   │   └── tests/
│   │       └── integration/
│   │
│   └── research-service/        # PubMed retrieval
│       ├── src/research_service/
│       │   ├── main.py
│       │   ├── pubmed_client.py
│       │   └── vector_store.py   # in-memory cache
│       └── tests/
│           └── integration/
│
├── migrations/                  # Alembic migrations
│   ├── alembic.ini
│   └── versions/
│
└── shared/                      # Shared Python package (minimal)
    └── src/shared/
```

---

## Technology Stack

### Frontend
- Placeholder only (no implemented UI).

### Backend Services
- Python 3.12
- FastAPI
- Pydantic
- httpx
- asyncpg
- redis (async)
- yt-dlp

### AI/ML Layer
- OpenAI Chat Completions API (direct httpx calls)

### Data Layer
- PostgreSQL 16
- Redis 7.x

### Infrastructure
- Docker
- Docker Compose

---

## Data Flow

### Analysis Request Flow

```
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant GW as API Gateway
    participant TS as Transcription Service
    participant AS as Analysis Service
    participant RS as Research Service
    participant DB as PostgreSQL
    participant Cache as Redis

    U->>FE: Submit YouTube URL
    FE->>GW: POST /api/v1/analysis
    GW->>Cache: Check rate limit
    GW->>DB: Create analysis record (pending)
    GW->>FE: Return analysis_id

    GW->>TS: Extract transcript + segments
    TS->>GW: Return transcript + segments + video metadata

    GW->>AS: Analyze transcript segments
    AS->>RS: Search evidence per claim
    RS->>RS: Cache in-memory results
    RS->>AS: Return evidence results
    AS->>GW: Return summary + claims + costs

    GW->>DB: Store claims, sources, and costs

    FE->>GW: Poll GET /api/v1/analysis/{id}
    GW->>FE: Return analysis results
```

---

## Database Schema

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,
    credits INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    youtube_url VARCHAR(500) NOT NULL,
    youtube_video_id VARCHAR(20) NOT NULL DEFAULT '',
    video_title VARCHAR(500),
    channel_name VARCHAR(255),
    video_duration INTEGER,
    thumbnail_url VARCHAR(500),
    status VARCHAR(20) DEFAULT 'pending',
    transcript TEXT,
    summary TEXT,
    overall_rating VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    is_public BOOLEAN DEFAULT true,

    total_pubmed_requests INTEGER DEFAULT 0,
    total_llm_prompt_tokens INTEGER DEFAULT 0,
    total_llm_completion_tokens INTEGER DEFAULT 0,
    report_llm_prompt_tokens INTEGER DEFAULT 0,
    report_llm_completion_tokens INTEGER DEFAULT 0,

    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    timestamp_start INTEGER,
    timestamp_end INTEGER,
    category VARCHAR(50),
    verdict VARCHAR(20),
    confidence FLOAT,
    explanation TEXT,

    pubmed_requests INTEGER DEFAULT 0,
    llm_prompt_tokens INTEGER DEFAULT 0,
    llm_completion_tokens INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    title VARCHAR(500),
    url VARCHAR(1000),
    source_type VARCHAR(50),
    publication_date DATE,
    relevance_score FLOAT,
    snippet TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_analyses_user_id ON analyses(user_id);
CREATE INDEX idx_analyses_status ON analyses(status);
CREATE INDEX idx_analyses_created_at ON analyses(created_at DESC);
CREATE INDEX idx_analyses_public_feed ON analyses(is_public, created_at DESC) WHERE status = 'completed';
CREATE INDEX idx_claims_analysis_id ON claims(analysis_id);
CREATE INDEX idx_sources_claim_id ON sources(claim_id);
```

---

## API Specification

### Base URL
```
Development: http://localhost:8000/api/v1
```

### Headers
- `x-user-email` (optional, used for credit tracking)

### Submit Analysis
```http
POST /analysis
Content-Type: application/json

{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "claims_per_chunk": 10,
  "chunk_size_chars": 5000,
  "research_max_results": 5,
  "research_sources": ["pubmed"],
  "is_public": true
}
```

Response 202:
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "estimated_time_seconds": 60,
  "poll_url": "/api/v1/analysis/550e8400-e29b-41d4-a716-446655440000"
}
```

### Get Analysis Status/Result
```http
GET /analysis/{analysis_id}
```

Response 200 (completed):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "video": {
    "youtube_id": "dQw4w9WgXcQ",
    "title": "10 Supplements You NEED for Longevity",
    "channel": "BiohackerX",
    "duration": 1234,
    "thumbnail_url": "https://..."
  },
  "summary": "This video makes 12 health claims...",
  "overall_rating": "mixed",
  "claims": [
    {
      "id": "claim-uuid",
      "text": "Vitamin D supplementation prevents all cancers",
      "timestamp": "2:34",
      "category": "supplements",
      "verdict": "unsupported_by_evidence",
      "confidence": 0.85,
      "explanation": "While vitamin D has shown some protective effects...",
      "sources": [
        {
          "title": "Vitamin D and Cancer Prevention: A Meta-Analysis",
          "url": "https://pubmed.ncbi.nlm.nih.gov/...",
          "type": "meta_analysis",
          "year": 2023,
          "snippet": "Results suggest modest reduction...",
          "relevance_score": 0.92
        }
      ],
      "costs": {
        "pubmed_requests": 1,
        "llm_prompt_tokens": 500,
        "llm_completion_tokens": 200
      }
    }
  ],
  "costs": {
    "pubmed_requests": 3,
    "llm_prompt_tokens": 3500,
    "llm_completion_tokens": 1200,
    "report_prompt_tokens": 400,
    "report_completion_tokens": 160
  },
  "created_at": "2026-02-11T10:30:00Z",
  "completed_at": "2026-02-11T10:31:23Z"
}
```

### Get Public Feed
```http
GET /feed?page=1&limit=20
```

Response 200:
```json
{
  "items": [
    {
      "id": "analysis-uuid",
      "video": {
        "youtube_id": "dQw4w9WgXcQ",
        "title": "10 Supplements You NEED for Longevity",
        "channel": "BiohackerX",
        "duration": 1234,
        "thumbnail_url": "https://..."
      },
      "summary": "This video makes 12 health claims...",
      "overall_rating": "mixed",
      "created_at": "2026-02-11T10:31:23Z"
    }
  ],
  "total": 156,
  "page": 1,
  "pages": 8
}
```

### Health Check
```http
GET /health
```

Response 200:
```json
{
  "status": "healthy",
  "services": {
    "database": "up",
    "redis": "up",
    "transcription_service": "up",
    "analysis_service": "up"
  },
  "version": "1.0.0"
}
```

---

## AI Prompts Architecture

### Claim Extraction Prompt
```python
CLAIM_EXTRACTION_PROMPT = """
You are a medical claim extraction specialist. Analyze the transcript and
extract all health-related claims suitable for verification.

Claims must be in English so they are easy to search in PubMed.

Return ONLY valid JSON. Do not include markdown, code fences, or extra text.

Return a JSON array with at most {claims_per_chunk} objects. Do not exceed this limit.

Return a JSON array of objects with fields:
- claim (string)
- category (string)
- timestamp (string or null, use the closest timestamp from the transcript if present, format m:ss or h:mm:ss)
- specificity (vague | specific | quantified)

Transcript (some lines include timestamps like [m:ss] or [h:mm:ss]):
{transcript}
"""
```

### Claim Analysis Prompt
```python
CLAIM_ANALYSIS_PROMPT = """
You are a medical research analyst. Evaluate the claim using the evidence.

Claim:
{claim}

Evidence:
{evidence}

Return ONLY valid JSON. Do not include markdown, code fences, or extra text.

Return a JSON object with fields:
- verdict (supported | unsupported_by_evidence | no_evidence_found)
- confidence (0.0-1.0)
- explanation (2-3 sentences)
- nuance (string or null)
"""
```

### Report Summary Prompt
```python
REPORT_PROMPT = """
You are summarizing a set of analyzed health claims for a report.
Provide:
- summary: 2-3 sentences overview
- overall_rating: accurate | mostly_accurate | mixed

Return ONLY valid JSON with keys "summary" and "overall_rating". Do not include
markdown, code fences, or extra text.

Claims:
{claims}
"""
```

---

## Configuration

### Environment Variables (selected)

```bash
# API Gateway
APP_ENV=development
APP_DEBUG=true
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=biohack_debunker
POSTGRES_USER=app
POSTGRES_PASSWORD=secure-password
DATABASE_URL=postgresql://app:secure-password@postgres:5432/biohack_debunker
REDIS_URL=redis://redis:6379/0
TRANSCRIPTION_SERVICE_URL=http://transcription-service:8001
ANALYSIS_SERVICE_URL=http://analysis-service:8002
RATE_LIMIT_REQUESTS=120
RATE_LIMIT_WINDOW=60
TRANSCRIPTION_READ_TIMEOUT=120
ANALYSIS_READ_TIMEOUT=600
ENABLE_PUBLIC_FEED=true
ENABLE_BILLING=false
FREE_TIER_CREDITS=3

# Analysis Service
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=16384
LLM_MAX_RETRIES=2
LLM_RETRY_BACKOFF=0.5
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
ANALYSIS_MAX_CONCURRENT_RESEARCH=5
RESEARCH_SERVICE_URL=http://research-service:8003

# Research Service
PUBMED_API_KEY=
PUBMED_BASE_URL=https://eutils.ncbi.nlm.nih.gov/entrez/eutils
RESEARCH_CACHE_TTL_SECONDS=3600
REDIS_URL=redis://redis:6379/0

# Transcription Service
YTDLP_BIN=yt-dlp
TRANSCRIPTION_MAX_CHARS=120000
```

---

## Quick Start

Prerequisites:
- Docker and Docker Compose v2
- OpenAI API key
- PubMed API key (optional)

Run locally:

```bash
cp .env.example .env
make up
make migrate
```

Access points:
- API Gateway: http://localhost:8000/docs
- Transcription: http://localhost:8001/health
- Analysis: http://localhost:8002/health
- Research: http://localhost:8003/health

---

## Testing Strategy

Tests live within each service:

```
services/api-gateway/tests/integration/
services/analysis-service/tests/integration/
services/research-service/tests/integration/
services/transcription-service/tests/integration/
services/transcription-service/tests/unit/
```

---

## Future Enhancements

- Real billing integration (Stripe or LemonSqueezy)
- Frontend UI implementation
- Whisper fallback for videos without subtitles
- Multi-language support
- User accounts with analysis history
- Public API for third-party integrations
- Observability stack (metrics + traces)

---

## License

MIT License - see LICENSE for details.

---

## Contributing

Contributions welcome! Please read CONTRIBUTING.md first.
