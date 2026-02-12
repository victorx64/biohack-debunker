from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3)
    max_results: int = Field(5, ge=1, le=25)
    sources: List[str] = Field(default_factory=lambda: ["pubmed"])


class ResearchSource(BaseModel):
    title: str
    url: str
    source_type: str
    publication_date: date | None = None
    publication_type: List[str] | None = None
    relevance_score: float = 0.0
    snippet: str | None = None


class ResearchResponse(BaseModel):
    query: str
    results: List[ResearchSource]
    cached: bool = False
    took_ms: int
    pubmed_requests: int = 0


class HealthResponse(BaseModel):
    status: str
    cache_entries: int
    cache_ttl_seconds: int
