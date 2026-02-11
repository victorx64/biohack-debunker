from __future__ import annotations

import os
import time
from typing import List

from fastapi import FastAPI, HTTPException
import redis.asyncio as redis

from .openalex_client import OpenAlexClient
from .pubmed_client import PubMedClient
from .schemas import HealthResponse, ResearchRequest, ResearchResponse, ResearchSource
from .tavily_client import TavilyClient
from .vector_store import CacheStore


app = FastAPI(title="Research Service", version="0.1.0")

CACHE_TTL_SECONDS = int(os.getenv("RESEARCH_CACHE_TTL_SECONDS", "3600"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_BASE_URL = os.getenv("TAVILY_BASE_URL", "https://api.tavily.com")
PUBMED_BASE_URL = os.getenv("PUBMED_BASE_URL", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY")
OPENALEX_BASE_URL = os.getenv("OPENALEX_BASE_URL", "https://api.openalex.org")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise RuntimeError("REDIS_URL is required for distributed PubMed rate limiting")

cache = CacheStore(ttl_seconds=CACHE_TTL_SECONDS)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY, base_url=TAVILY_BASE_URL)
redis_client = redis.from_url(REDIS_URL)
pubmed_client = PubMedClient(
    base_url=PUBMED_BASE_URL,
    api_key=PUBMED_API_KEY,
    redis_client=redis_client,
)
openalex_client = OpenAlexClient(api_key=OPENALEX_API_KEY, base_url=OPENALEX_BASE_URL)


def _normalize_keywords(value: List[str] | None) -> List[str]:
    if not value:
        return []
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


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
    keywords = _normalize_keywords(request.keywords)
    keyword_key = ",".join(keywords) if keywords else ""
    cache_key = f"{request.query}::{keyword_key}::{','.join(sorted(sources))}::{request.max_results}"

    cached = cache.get(cache_key)
    if cached:
        took_ms = int((time.perf_counter() - start) * 1000)
        return ResearchResponse(
            query=request.query,
            results=cached.results,
            cached=True,
            took_ms=took_ms,
            tavily_requests=cached.tavily_requests,
            pubmed_requests=cached.pubmed_requests,
            openalex_requests=cached.openalex_requests,
        )

    results: List[ResearchSource] = []
    tavily_requests = 0
    pubmed_requests = 0
    openalex_requests = 0
    try:
        if "tavily" in sources:
            tavily_query = " ".join(keywords) if keywords else request.query
            results.extend(await tavily_client.search(tavily_query, request.max_results))
            tavily_requests = 1
        if "pubmed" in sources:
            pubmed_query = " ".join(keywords) if keywords else request.query
            results.extend(await pubmed_client.search(pubmed_query, request.max_results))
            pubmed_requests = 1
        if "openalex" in sources:
            openalex_query = " ".join(keywords) if keywords else request.query
            results.extend(await openalex_client.search(openalex_query, request.max_results))
            openalex_requests = 1
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
        tavily_requests=tavily_requests,
        pubmed_requests=pubmed_requests,
        openalex_requests=openalex_requests,
    )
    cache.set(cache_key, response)
    return response
