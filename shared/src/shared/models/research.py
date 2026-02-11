from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel, Field


class ResearchQuery(BaseModel):
    query: str = Field(..., min_length=3)
    max_results: int = Field(5, ge=1, le=20)


class ResearchSource(BaseModel):
    title: str
    url: str
    source_type: str
    publication_date: date | None = None
    publication_type: str | None = None
    relevance_score: float = 0.0
    snippet: str | None = None


class ResearchResults(BaseModel):
    query: str
    results: List[ResearchSource]
