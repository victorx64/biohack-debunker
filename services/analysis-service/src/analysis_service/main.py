from __future__ import annotations

import asyncio
import os
import time
from typing import List

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


app = FastAPI(title="Analysis Service", version="0.1.0")

RESEARCH_SERVICE_BASE = os.getenv("RESEARCH_SERVICE_URL", "http://research-service:8003")
RESEARCH_ENDPOINT = _join_url(RESEARCH_SERVICE_BASE, "/research")
MAX_CONCURRENT_RESEARCH = _env_int("ANALYSIS_MAX_CONCURRENT_RESEARCH", 5)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "stub").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.2)
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 800)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


@app.on_event("startup")
async def startup() -> None:
    api_key = OPENAI_API_KEY if LLM_PROVIDER == "openai" else ANTHROPIC_API_KEY
    app.state.llm_client = LLMClient(
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        api_key=api_key,
        base_url=None,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )
    app.state.http_client = httpx.AsyncClient(timeout=30)


@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.http_client.aclose()


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
        warnings.append("LLM not configured; using heuristic extraction and analysis.")

    claims = await extract_claims(request.transcript, request.max_claims, llm)
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
        analysis = await analyze_claim(claim.claim, sources, llm)
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
    summary, overall_rating = await generate_report(results, llm)

    took_ms = int((time.perf_counter() - start) * 1000)
    return AnalysisResponse(
        claims=results,
        summary=summary,
        overall_rating=overall_rating,
        took_ms=took_ms,
        warnings=warnings,
    )
