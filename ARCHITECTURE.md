# BioHack Debunker - AI-Powered Health Claims Analyzer

> Analyze YouTube videos from biohackers and health influencers. Get evidence-based fact-checks powered by the latest medical research.

## 🎯 Project Overview

**Problem:** Health misinformation spreads rapidly on YouTube. Viewers lack time and expertise to verify claims against scientific literature.

**Solution:** An AI service that:
1. Extracts claims from YouTube videos (via subtitles)
2. Cross-references them with peer-reviewed medical research
3. Provides evidence-based analysis with citations

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DOCKER COMPOSE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────────────────────────────────────┐ │
│  │              │     │              API GATEWAY (FastAPI)               │ │
│  │   Frontend   │────▶│  - Rate Limiting    - Request Routing           │ │
│  │   (Next.js)  │     │  - Auth Middleware  - API Versioning            │ │
│  │   Port 3000  │     │  Port 8000                                      │ │
│  └──────────────┘     └─────────┬────────────────┬───────────────┬──────┘ │
│                                 │                │               │        │
│                    ┌────────────┴───┐ ┌─────────┴────┐ ┌────────┴──────┐ │
│                    │                │ │              │ │               │ │
│                    │  Transcription │ │   Analysis   │ │   Research    │ │
│                    │    Service     │ │   Service    │ │    Service    │ │
│                    │    (Python)    │ │   (Python)   │ │   (Python)    │ │
│                    │    Port 8001   │ │   Port 8002  │ │   Port 8003   │ │
│                    │                │ │              │ │               │ │
│                    └───────┬────────┘ └──────┬───────┘ └───────┬───────┘ │
│                            │                 │                 │         │
│                            │         ┌──────┴───────┐         │         │
│                            │         │              │         │         │
│                            │         │   LangChain  │◀────────┘         │
│                            │         │   + Tavily   │                   │
│                            │         │              │                   │
│                            │         └──────────────┘                   │
│                            │                                            │
│  ┌─────────────────────────┴────────────────────────────────────────┐  │
│  │                        DATA LAYER                                 │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │  │
│  │  │ PostgreSQL │  │   Redis    │  │  Qdrant    │  │   MinIO    │  │  │
│  │  │  (Main DB) │  │  (Cache/   │  │  (Vector   │  │  (Object   │  │  │
│  │  │  Port 5432 │  │   Queue)   │  │   Store)   │  │   Store)   │  │  │
│  │  │            │  │  Port 6379 │  │  Port 6333 │  │  Port 9000 │  │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
biohack-debunker/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── Makefile
│
├── frontend/                    # Next.js 14 App Router
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                 # Landing + URL input
│   │   │   ├── analysis/[id]/page.tsx   # Analysis results
│   │   │   ├── feed/page.tsx            # Public feed of analyses
│   │   │   └── api/                      # API routes (BFF pattern)
│   │   ├── components/
│   │   │   ├── ui/                       # shadcn/ui components
│   │   │   ├── VideoInput.tsx
│   │   │   ├── AnalysisCard.tsx
│   │   │   ├── ClaimCard.tsx
│   │   │   └── SourceCitation.tsx
│   │   └── lib/
│   │       ├── api-client.ts
│   │       └── utils.ts
│   └── tailwind.config.js
│
├── services/
│   │
│   ├── api-gateway/             # FastAPI - Main entry point
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── routers/
│   │       │   ├── analysis.py          # POST /api/v1/analysis
│   │       │   ├── feed.py              # GET /api/v1/feed
│   │       │   └── health.py
│   │       ├── middleware/
│   │       │   ├── rate_limit.py
│   │       │   └── auth.py              # Mock billing/credits
│   │       ├── schemas/
│   │       │   ├── requests.py
│   │       │   └── responses.py
│   │       └── services/
│   │           └── orchestrator.py      # Coordinates microservices
│   │
│   ├── transcription-service/   # YouTube subtitle extraction
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── main.py                  # FastAPI app
│   │       ├── youtube_client.py        # yt-dlp integration
│   │       ├── transcript_parser.py
│   │       └── schemas.py
│   │
│   ├── analysis-service/        # LangChain claim extraction & analysis
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── main.py
│   │       ├── chains/
│   │       │   ├── claim_extractor.py   # Extract health claims
│   │       │   ├── claim_analyzer.py    # Analyze with research
│   │       │   └── report_generator.py  # Final report
│   │       ├── prompts/
│   │       │   ├── extraction.py
│   │       │   └── analysis.py
│   │       ├── models.py
│   │       └── schemas.py
│   │
│   └── research-service/        # Medical research retrieval
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/
│           ├── main.py
│           ├── tavily_client.py         # Tavily search integration
│           ├── pubmed_client.py         # PubMed API (optional)
│           ├── vector_store.py          # Qdrant for caching
│           └── schemas.py
│
├── shared/                      # Shared Python package
│   ├── pyproject.toml
│   └── src/
│       └── shared/
│           ├── __init__.py
│           ├── models/                  # Pydantic models
│           │   ├── video.py
│           │   ├── claim.py
│           │   └── analysis.py
│           ├── database/
│           │   ├── connection.py
│           │   └── repositories/
│           └── messaging/
│               └── redis_client.py
│
├── migrations/                  # Alembic migrations
│   ├── alembic.ini
│   └── versions/
│
└── scripts/
    ├── seed_data.py
    └── run_tests.sh
```

---

## 🔧 Technology Stack

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| **Next.js** | 14.x | React framework with App Router, SSR/SSG |
| **TypeScript** | 5.x | Type safety |
| **Tailwind CSS** | 3.x | Utility-first styling |
| **shadcn/ui** | latest | Accessible UI components |
| **TanStack Query** | 5.x | Server state management |
| **Zustand** | 4.x | Client state (if needed) |

### Backend Services
| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.12 | Primary backend language |
| **FastAPI** | 0.110+ | High-performance async API framework |
| **Pydantic** | 2.x | Data validation and serialization |
| **LangChain** | 0.2+ | LLM orchestration framework |
| **LangGraph** | 0.1+ | Complex AI workflows (optional) |
| **yt-dlp** | latest | YouTube metadata & subtitles extraction |
| **httpx** | 0.27+ | Async HTTP client |
| **uvicorn** | 0.29+ | ASGI server |

### AI/ML Layer
| Technology | Purpose |
|------------|---------|
| **OpenAI GPT-4o** | Primary LLM for analysis (via LangChain) |
| **Anthropic Claude** | Alternative LLM (configurable) |
| **Tavily API** | Real-time medical research search |
| **Qdrant** | Vector database for semantic caching |

### Data Layer
| Technology | Version | Purpose |
|------------|---------|---------|
| **PostgreSQL** | 16 | Primary relational database |
| **Redis** | 7.x | Caching, rate limiting, job queue |
| **Qdrant** | 1.8+ | Vector similarity search |
| **MinIO** | latest | S3-compatible object storage (reports, cache) |

### Infrastructure
| Technology | Purpose |
|------------|---------|
| **Docker** | Containerization |
| **Docker Compose** | Local orchestration |
| **Traefik** | Reverse proxy, SSL (production) |
| **GitHub Actions** | CI/CD pipeline |

---

## 🔄 Data Flow

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
    GW->>GW: Validate credits (mock)
    GW->>DB: Create analysis record (status: pending)
    GW->>FE: Return analysis_id
    
    GW->>TS: Extract transcript
    TS->>TS: Fetch YouTube subtitles (yt-dlp)
    TS->>GW: Return transcript + metadata
    
    GW->>AS: Analyze transcript
    AS->>AS: Extract health claims (LangChain)
    
    loop For each claim
        AS->>RS: Search for evidence
        RS->>RS: Query Tavily API
        RS->>RS: Cache in Qdrant
        RS->>AS: Return research results
    end
    
    AS->>AS: Generate analysis report
    AS->>GW: Return complete analysis
    
    GW->>DB: Update analysis (status: complete)
    GW->>Cache: Invalidate feed cache
    
    FE->>GW: Poll GET /api/v1/analysis/{id}
    GW->>FE: Return analysis results
    FE->>U: Display analysis
```

---

## 📊 Database Schema

```sql
-- Core tables

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,
    credits INTEGER DEFAULT 3,  -- Free tier
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    youtube_url VARCHAR(500) NOT NULL,
    youtube_video_id VARCHAR(20) NOT NULL,
    video_title VARCHAR(500),
    channel_name VARCHAR(255),
    video_duration INTEGER,  -- seconds
    thumbnail_url VARCHAR(500),
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    transcript TEXT,
    summary TEXT,
    overall_rating VARCHAR(20),  -- accurate, mostly_accurate, mixed, misleading
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    is_public BOOLEAN DEFAULT true,
    
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES analyses(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    timestamp_start INTEGER,  -- seconds in video
    timestamp_end INTEGER,
    category VARCHAR(50),  -- nutrition, supplements, exercise, sleep, etc.
    verdict VARCHAR(20),  -- supported, partially_supported, unsupported, misleading
    confidence FLOAT,
    explanation TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID REFERENCES claims(id) ON DELETE CASCADE,
    title VARCHAR(500),
    url VARCHAR(1000),
    source_type VARCHAR(50),  -- pubmed, clinical_trial, meta_analysis, review
    publication_date DATE,
    relevance_score FLOAT,
    snippet TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_analyses_user_id ON analyses(user_id);
CREATE INDEX idx_analyses_status ON analyses(status);
CREATE INDEX idx_analyses_created_at ON analyses(created_at DESC);
CREATE INDEX idx_analyses_public_feed ON analyses(is_public, created_at DESC) WHERE status = 'completed';
CREATE INDEX idx_claims_analysis_id ON claims(analysis_id);
CREATE INDEX idx_sources_claim_id ON sources(claim_id);
```

---

## 🔌 API Specification

### Base URL
```
Development: http://localhost:8000/api/v1
Production:  https://api.biohack-debunker.com/api/v1
```

### Endpoints

#### Submit Analysis
```http
POST /analysis
Content-Type: application/json

{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}

Response 202:
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "estimated_time_seconds": 60,
  "poll_url": "/api/v1/analysis/550e8400-e29b-41d4-a716-446655440000"
}
```

#### Get Analysis Status/Result
```http
GET /analysis/{analysis_id}

Response 200 (completed):
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
      "verdict": "partially_supported",
      "confidence": 0.85,
      "explanation": "While vitamin D has shown some protective effects...",
      "sources": [
        {
          "title": "Vitamin D and Cancer Prevention: A Meta-Analysis",
          "url": "https://pubmed.ncbi.nlm.nih.gov/...",
          "type": "meta_analysis",
          "year": 2023,
          "snippet": "Results suggest modest reduction in..."
        }
      ]
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:31:23Z"
}
```

#### Get Public Feed
```http
GET /feed?page=1&limit=20

Response 200:
{
  "items": [...],
  "total": 156,
  "page": 1,
  "pages": 8
}
```

#### Health Check
```http
GET /health

Response 200:
{
  "status": "healthy",
  "services": {
    "database": "up",
    "redis": "up",
    "qdrant": "up"
  },
  "version": "1.0.0"
}
```

---

## 🤖 AI Prompts Architecture

### Claim Extraction Prompt
```python
CLAIM_EXTRACTION_PROMPT = """
You are a medical claim extraction specialist. Analyze the following 
transcript from a health/biohacking YouTube video.

Extract ALL health-related claims made in the video. For each claim:
1. Quote the exact claim or paraphrase if too long
2. Identify the timestamp (if available from context)
3. Categorize: nutrition, supplements, exercise, sleep, longevity, 
   mental_health, biohacking, medical_procedure, other
4. Rate claim specificity: vague, specific, quantified

Focus on claims that are:
- Testable against scientific literature
- Related to health outcomes
- Presented as factual (not clearly labeled as opinion)

TRANSCRIPT:
{transcript}

Return as JSON array of claims.
"""
```

### Claim Analysis Prompt
```python
CLAIM_ANALYSIS_PROMPT = """
You are a medical research analyst. Evaluate the following health claim 
against the provided research evidence.

CLAIM: {claim}

RESEARCH EVIDENCE:
{research_results}

Provide:
1. VERDICT: supported | partially_supported | unsupported | misleading
2. CONFIDENCE: 0.0-1.0 based on evidence quality and relevance
3. EXPLANATION: 2-3 sentences explaining your verdict in accessible language
4. NUANCE: Important caveats or context the video may have missed

Be balanced and scientific. Avoid absolute statements unless evidence is 
overwhelming. Acknowledge when evidence is limited or conflicting.
"""
```

---

## ⚙️ Configuration

### Environment Variables

```bash
# .env.example

# === Application ===
APP_ENV=development  # development | staging | production
APP_DEBUG=true
APP_SECRET_KEY=your-secret-key-min-32-chars

# === Database ===
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=biohack_debunker
POSTGRES_USER=app
POSTGRES_PASSWORD=secure-password

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === Qdrant ===
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# === AI Services ===
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...  # Optional fallback
TAVILY_API_KEY=tvly-...

# === LLM Configuration ===
LLM_PROVIDER=openai  # openai | anthropic
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4096

# === Rate Limiting ===
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=3600  # seconds

# === Feature Flags ===
ENABLE_PUBLIC_FEED=true
ENABLE_BILLING=false  # Mock mode
FREE_TIER_CREDITS=3
```

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose v2
- OpenAI API key
- Tavily API key (free tier available)

### Run Locally

```bash
# Clone repository
git clone https://github.com/yourusername/biohack-debunker.git
cd biohack-debunker

# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
nano .env

# Start all services
make up

# Or with docker compose directly
docker compose up -d

# View logs
make logs

# Run database migrations
make migrate

# Seed sample data (optional)
make seed
```

### Access Points
- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs (Swagger UI)
- **API ReDoc:** http://localhost:8000/redoc

---

## 🧪 Testing Strategy

```bash
# Run all tests
make test

# Run specific service tests
make test-analysis

# Run with coverage
make test-coverage

# E2E tests
make test-e2e
```

### Test Structure
```
tests/
├── unit/
│   ├── test_claim_extractor.py
│   ├── test_youtube_client.py
│   └── test_schemas.py
├── integration/
│   ├── test_analysis_flow.py
│   └── test_research_service.py
└── e2e/
    └── test_full_analysis.py
```

---

## 📈 Future Enhancements (v2+)

- [ ] **Real billing integration** (Stripe/LemonSqueezy)
- [ ] **Browser extension** for inline YouTube analysis
- [ ] **Whisper fallback** for videos without subtitles
- [ ] **Multi-language support**
- [ ] **User accounts** with analysis history
- [ ] **API for third-party integrations**
- [ ] **Kubernetes manifests** for production scaling
- [ ] **Prometheus + Grafana** monitoring stack

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

---

*Built with ❤️ to fight health misinformation*