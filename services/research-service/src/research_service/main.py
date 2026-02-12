from __future__ import annotations

import os
import time
from typing import List

from fastapi import FastAPI, HTTPException
import redis.asyncio as redis

from .pubmed_client import PubMedClient
from .schemas import HealthResponse, ResearchRequest, ResearchResponse, ResearchSource
from .vector_store import CacheStore


app = FastAPI(title="Research Service", version="0.1.0")

CACHE_TTL_SECONDS = int(os.getenv("RESEARCH_CACHE_TTL_SECONDS", "3600"))
PUBMED_BASE_URL = os.getenv("PUBMED_BASE_URL", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise RuntimeError("REDIS_URL is required for distributed PubMed rate limiting")

cache = CacheStore(ttl_seconds=CACHE_TTL_SECONDS)
redis_client = redis.from_url(REDIS_URL)
pubmed_client = PubMedClient(
    base_url=PUBMED_BASE_URL,
    api_key=PUBMED_API_KEY,
    redis_client=redis_client,
)


@app.on_event("shutdown")
async def shutdown() -> None:
    if redis_client is not None:
        await redis_client.close()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        cache_entries=cache.size(),
        cache_ttl_seconds=cache.ttl_seconds,
    )


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    start = time.perf_counter()
    sources = [source.strip().lower() for source in request.sources]
    unsupported = sorted({source for source in sources if source != "pubmed"})
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported research sources: {', '.join(unsupported)}",
        )
    cache_key = f"{request.query}::{','.join(sorted(sources))}::{request.max_results}"

    cached = cache.get(cache_key)
    if cached:
        took_ms = int((time.perf_counter() - start) * 1000)
        return ResearchResponse(
            query=request.query,
            results=cached.results,
            cached=True,
            took_ms=took_ms,
            pubmed_requests=cached.pubmed_requests,
        )

    results: List[ResearchSource] = []
    pubmed_requests = 0
    try:
        if "pubmed" in sources:
            results.extend(await pubmed_client.search(request.query, request.max_results))
            pubmed_requests = 1
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    results.sort(key=lambda item: item.relevance_score, reverse=True)
    results = results[: request.max_results]

    took_ms = int((time.perf_counter() - start) * 1000)
    response = ResearchResponse(
        query=request.query,
        results=results,
        cached=False,
        took_ms=took_ms,
        pubmed_requests=pubmed_requests,
    )
    cache.set(cache_key, response)
    return response
