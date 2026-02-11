from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel, Field


class ResearchQuery(BaseModel):
    query: str = Field(..., min_length=3)
    max_results: int = Field(5, ge=1, le=20)


class CountsByYear(BaseModel):
    year: int
    cited_by_count: int = 0
    works_count: int = 0


class ResearchSource(BaseModel):
    title: str
    url: str
    source_type: str
    publication_date: date | None = None
    publication_type: List[str] | None = None
    relevance_score: float = 0.0
    snippet: str | None = None
    cited_by_count: int | None = None
    fwci: float | None = None
    citation_normalized_percentile: float | None = None
    primary_source_display_name: str | None = None
    primary_source_is_core: bool | None = None
    counts_by_year: List[CountsByYear] | None = None
    institution_display_names: List[str] | None = None


class ResearchResults(BaseModel):
    query: str
    results: List[ResearchSource]
