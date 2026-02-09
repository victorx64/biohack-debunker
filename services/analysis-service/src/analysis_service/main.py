from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

import httpx
from fastapi import FastAPI, HTTPException

from .chains.claim_analyzer import analyze_claim, fetch_research
from .chains.claim_extractor import extract_claims
from .chains.report_generator import generate_report
from .llm_client import LLMClient
from .schemas import AnalysisRequest, AnalysisResponse, ClaimResult, EvidenceSource, HealthResponse


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


RESEARCH_SERVICE_BASE = os.getenv("RESEARCH_SERVICE_URL", "http://research-service:8003")
RESEARCH_ENDPOINT = _join_url(RESEARCH_SERVICE_BASE, "/research")
MAX_CONCURRENT_RESEARCH = _env_int("ANALYSIS_MAX_CONCURRENT_RESEARCH", 5)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.2)
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 800)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    api_key = OPENAI_API_KEY if LLM_PROVIDER == "openai" else ANTHROPIC_API_KEY
    base_url = OPENAI_BASE_URL if LLM_PROVIDER == "openai" else ANTHROPIC_BASE_URL
    app.state.llm_client = LLMClient(
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        api_key=api_key,
        base_url=base_url,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )
    app.state.http_client = httpx.AsyncClient(timeout=30)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Analysis Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        llm_provider=LLM_PROVIDER,
        research_service_url=RESEARCH_SERVICE_BASE,
    )


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    start = time.perf_counter()
    warnings: List[str] = []

    llm: LLMClient = app.state.llm_client
    client: httpx.AsyncClient = app.state.http_client
    if not llm.enabled:
        raise HTTPException(status_code=503, detail="LLM client is not configured")

    try:
        claims = await extract_claims(request.transcript, request.max_claims, llm)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not claims:
        raise HTTPException(status_code=400, detail="No claims extracted from transcript")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_RESEARCH)

    async def process_claim(claim) -> ClaimResult:
        sources: List[EvidenceSource] = []
        try:
            async with semaphore:
                sources = await fetch_research(
                    client,
                    RESEARCH_ENDPOINT,
                    claim.claim,
                    request.research_max_results,
                    request.research_sources,
                )
        except Exception as exc:
            warnings.append(f"Research lookup failed for claim: {claim.claim[:80]} ({exc})")
        try:
            analysis = await analyze_claim(claim.claim, sources, llm)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ClaimResult(
            claim=claim.claim,
            category=claim.category,
            timestamp=claim.timestamp,
            specificity=claim.specificity,
            verdict=analysis.verdict,
            confidence=analysis.confidence,
            explanation=analysis.explanation,
            nuance=analysis.nuance,
            sources=sources,
        )

    results = await asyncio.gather(*(process_claim(item) for item in claims))
    try:
        summary, overall_rating = await generate_report(results, llm)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    took_ms = int((time.perf_counter() - start) * 1000)
    return AnalysisResponse(
        claims=results,
        summary=summary,
        overall_rating=overall_rating,
        took_ms=took_ms,
        warnings=warnings,
    )
