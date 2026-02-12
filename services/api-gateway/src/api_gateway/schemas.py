from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class AnalysisCreateRequest(BaseModel):
    youtube_url: str = Field(..., min_length=10)
    force: bool = False
    claims_per_chunk: int = Field(7, ge=1, le=30)
    chunk_size_chars: int = Field(4000, ge=500, le=20000)
    research_max_results: int = Field(25, ge=1, le=25)
    research_sources: List[str] = Field(default_factory=lambda: ["pubmed"])
    is_public: bool = True


class AnalysisCreateResponse(BaseModel):
    analysis_id: UUID
    status: str
    estimated_time_seconds: int
    poll_url: str


class VideoInfo(BaseModel):
    youtube_id: str
    title: str | None = None
    channel: str | None = None
    duration: int | None = None
    thumbnail_url: str | None = None


class SourceInfo(BaseModel):
    title: str
    url: str
    type: str
    year: int | None = None
    publication_type: List[str] | None = None
    snippet: str | None = None
    relevance_score: float | None = None


class ClaimInfo(BaseModel):
    id: UUID
    text: str
    timestamp: str | None = None
    category: str | None = None
    search_query: str | None = None
    verdict: str | None = None
    confidence: float | None = None
    explanation: str | None = None
    evidence_level: str | None = None
    study_type: str | None = None
    sources: List[SourceInfo] = Field(default_factory=list)
    costs: "ClaimCosts" = Field(default_factory=lambda: ClaimCosts())


class ClaimCosts(BaseModel):
    pubmed_requests: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0


class AnalysisCosts(BaseModel):
    pubmed_requests: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    report_prompt_tokens: int = 0
    report_completion_tokens: int = 0


class AnalysisDetailResponse(BaseModel):
    id: UUID
    status: str
    video: VideoInfo | None = None
    summary: str | None = None
    overall_rating: str | None = None
    claims: List[ClaimInfo] = Field(default_factory=list)
    costs: AnalysisCosts = Field(default_factory=lambda: AnalysisCosts())
    created_at: datetime | None = None
    completed_at: datetime | None = None


class FeedItem(BaseModel):
    id: UUID
    video: VideoInfo | None = None
    summary: str | None = None
    overall_rating: str | None = None
    created_at: datetime | None = None


class FeedResponse(BaseModel):
    items: List[FeedItem]
    total: int
    page: int
    pages: int


class HealthResponse(BaseModel):
    status: str
    services: dict
    version: str = "1.0.0"
