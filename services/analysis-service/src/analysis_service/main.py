from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

import httpx
from fastapi import FastAPI, HTTPException, Request

from .chains.claim_analyzer import analyze_claim, fetch_research
from .chains.claim_extractor import extract_claims
from .chains.report_generator import generate_report
from .llm_client import LLMClient
from .observability import (
    configure_logging,
    correlation_headers,
    metrics_response,
    observability_middleware,
    observe_llm_tokens,
    observe_pubmed_calls,
    set_analysis_id,
)
from .schemas import (
    AnalysisCosts,
    AnalysisRequest,
    AnalysisResponse,
    ClaimCosts,
    ClaimResult,
    EvidenceSource,
    HealthResponse,
)


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

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger("analysis_service")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.2)
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 16384)
LLM_MAX_RETRIES = _env_int("LLM_MAX_RETRIES", 2)
LLM_RETRY_BACKOFF = _env_float("LLM_RETRY_BACKOFF", 0.5)
LLM_TIMEOUT = _env_float("LLM_TIMEOUT", 30.0)
LLM_READ_TIMEOUT = _env_float("LLM_READ_TIMEOUT", 120.0)
LLM_RESPONSE_FORMAT = os.getenv("LLM_RESPONSE_FORMAT", "").strip().lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    api_key = OPENAI_API_KEY if LLM_PROVIDER == "openai" else None
    base_url = OPENAI_BASE_URL if LLM_PROVIDER == "openai" else None
    response_format = {"type": "json_object"} if LLM_RESPONSE_FORMAT == "json_object" else None
    app.state.llm_client = LLMClient(
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        api_key=api_key,
        base_url=base_url,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        response_format=response_format,
        timeout=LLM_TIMEOUT,
        read_timeout=LLM_READ_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
        backoff_seconds=LLM_RETRY_BACKOFF,
    )
    app.state.http_client = httpx.AsyncClient(timeout=30)
    logger.info(
        "analysis service starting provider=%s model=%s research_url=%s max_concurrent_research=%s",
        LLM_PROVIDER or "(unset)",
        LLM_MODEL or "(unset)",
        RESEARCH_ENDPOINT,
        MAX_CONCURRENT_RESEARCH,
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Analysis Service", version="0.1.0", lifespan=lifespan)
configure_logging("analysis-service")
app.middleware("http")(observability_middleware)


@app.get("/metrics")
async def metrics():
    return metrics_response()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        llm_provider=LLM_PROVIDER,
        research_service_url=RESEARCH_SERVICE_BASE,
    )


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest, http_request: Request) -> AnalysisResponse:
    start = time.perf_counter()
    warnings: List[str] = []
    set_analysis_id(getattr(http_request.state, "analysis_id", None))

    logger.info(
        "analyze request segments=%s claims_per_chunk=%s chunk_size_chars=%s research_max_results=%s sources=%s",
        len(request.segments),
        request.claims_per_chunk,
        request.chunk_size_chars,
        request.research_max_results,
        ",".join(request.research_sources),
    )

    llm: LLMClient = app.state.llm_client
    client: httpx.AsyncClient = app.state.http_client
    if not llm.enabled:
        logger.error("LLM client not configured provider=%s model=%s", LLM_PROVIDER, LLM_MODEL)
        raise HTTPException(status_code=503, detail="LLM client is not configured")

    try:
        logger.info("claim extraction started")
        claims = await extract_claims(
            request.segments,
            request.claims_per_chunk,
            request.chunk_size_chars,
            llm,
        )
    except Exception as exc:
        logger.exception("claim extraction failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not claims:
        logger.warning("claim extraction returned no claims")
        raise HTTPException(status_code=400, detail="No claims extracted from transcript")

    logger.info("claim extraction success claims=%s", len(claims))

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_RESEARCH)

    async def process_claim(index: int, claim) -> ClaimResult:
        logger.info("analysis progress claim=%s/%s stage=research", index, len(claims))
        sources: List[EvidenceSource] = []
        research_usage = {"pubmed_requests": 0}
        try:
            async with semaphore:
                sources, research_usage = await fetch_research(
                    client,
                    RESEARCH_ENDPOINT,
                    claim.claim,
                    claim.search_query,
                    request.research_max_results,
                    request.research_sources,
                    headers=correlation_headers(),
                )
        except Exception as exc:
            warnings.append(f"Research lookup failed for claim: {claim.claim[:80]} ({exc})")
            logger.warning(
                "research lookup failed claim=%s error=%s",
                claim.claim[:120],
                exc,
            )
        logger.info("analysis progress claim=%s/%s stage=verdict", index, len(claims))
        try:
            analysis, usage = await analyze_claim(
                claim.claim,
                sources,
                llm,
                claim_index=index,
                claims_total=len(claims),
            )
        except Exception as exc:
            logger.exception("claim analysis failed claim=%s", claim.claim[:120])
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        logger.info("analysis progress claim=%s/%s stage=done", index, len(claims))
        return ClaimResult(
            claim=claim.claim,
            timestamp=claim.timestamp,
            search_query=claim.search_query,
            verdict=analysis.verdict,
            confidence=analysis.confidence,
            explanation=analysis.explanation,
            nuance=analysis.nuance,
            sources=sources,
            costs=ClaimCosts(
                pubmed_requests=research_usage.get("pubmed_requests", 0),
                llm_prompt_tokens=usage.prompt_tokens,
                llm_completion_tokens=usage.completion_tokens,
            ),
        )

    results = await asyncio.gather(
        *(process_claim(index, item) for index, item in enumerate(claims, start=1))
    )
    try:
        logger.info("report generation started")
        summary, overall_rating, report_usage = await generate_report(results, llm)
    except Exception as exc:
        logger.exception("report generation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    total_pubmed = sum(item.costs.pubmed_requests for item in results)
    total_prompt_tokens = sum(item.costs.llm_prompt_tokens for item in results)
    total_completion_tokens = sum(item.costs.llm_completion_tokens for item in results)
    total_prompt_tokens += report_usage.prompt_tokens
    total_completion_tokens += report_usage.completion_tokens
    observe_pubmed_calls(total_pubmed, endpoint="/research")
    observe_llm_tokens("prompt", total_prompt_tokens)
    observe_llm_tokens("completion", total_completion_tokens)
    observe_llm_tokens("report_prompt", report_usage.prompt_tokens)
    observe_llm_tokens("report_completion", report_usage.completion_tokens)

    took_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "analyze completed claims=%s took_ms=%s warnings=%s tokens_prompt=%s tokens_completion=%s pubmed_requests=%s",
        len(results),
        took_ms,
        len(warnings),
        total_prompt_tokens,
        total_completion_tokens,
        total_pubmed,
    )
    return AnalysisResponse(
        claims=results,
        summary=summary,
        overall_rating=overall_rating,
        took_ms=took_ms,
        warnings=warnings,
        costs=AnalysisCosts(
            pubmed_requests=total_pubmed,
            llm_prompt_tokens=total_prompt_tokens,
            llm_completion_tokens=total_completion_tokens,
            report_prompt_tokens=report_usage.prompt_tokens,
            report_completion_tokens=report_usage.completion_tokens,
        ),
    )
