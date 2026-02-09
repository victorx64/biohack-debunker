from __future__ import annotations

import os
import time
from typing import List

from fastapi import FastAPI, HTTPException

from .pubmed_client import PubMedClient
from .schemas import HealthResponse, ResearchRequest, ResearchResponse, ResearchSource
from .tavily_client import TavilyClient
from .vector_store import CacheStore


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _stub_results(query: str, max_results: int) -> List[ResearchSource]:
    samples = [
        ResearchSource(
            title="Vitamin D and all-cause mortality: an umbrella review",
            url="https://pubmed.ncbi.nlm.nih.gov/",
            source_type="stub",
            relevance_score=0.8,
            snippet=f"Stubbed evidence for query: {query}",
        ),
        ResearchSource(
            title="Exercise and cardiovascular risk: meta-analysis",
            url="https://pubmed.ncbi.nlm.nih.gov/",
            source_type="stub",
            relevance_score=0.7,
            snippet="Stubbed evidence sample (replace with real search results).",
        ),
    ]
    return samples[:max_results]


app = FastAPI(title="Research Service", version="0.1.0")

USE_STUBS = _env_bool("RESEARCH_USE_STUBS", True)
CACHE_TTL_SECONDS = int(os.getenv("RESEARCH_CACHE_TTL_SECONDS", "3600"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

cache = CacheStore(ttl_seconds=CACHE_TTL_SECONDS)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
pubmed_client = PubMedClient()


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
    cache_key = f"{request.query}::{','.join(sorted(sources))}::{request.max_results}"

    cached = cache.get(cache_key)
    if cached:
        took_ms = int((time.perf_counter() - start) * 1000)
        return ResearchResponse(
            query=request.query,
            results=cached.results,
            cached=True,
            took_ms=took_ms,
        )

    if USE_STUBS:
        results = _stub_results(request.query, request.max_results)
    else:
        results: List[ResearchSource] = []
        try:
            if "tavily" in sources:
                results.extend(await tavily_client.search(request.query, request.max_results))
            if "pubmed" in sources:
                results.extend(await pubmed_client.search(request.query, request.max_results))
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
    )
    cache.set(cache_key, response)
    return response
