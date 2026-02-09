from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    transcript: str = Field(..., min_length=20)
    max_claims: int = Field(8, ge=1, le=30)
    research_max_results: int = Field(5, ge=1, le=20)
    research_sources: List[str] = Field(default_factory=lambda: ["tavily", "pubmed"])


class ClaimDraft(BaseModel):
    claim: str
    category: str | None = None
    timestamp: str | None = None
    specificity: str | None = None


class EvidenceSource(BaseModel):
    title: str
    url: str
    source_type: str
    relevance_score: float = 0.0
    snippet: str | None = None


class ClaimAnalysis(BaseModel):
    verdict: str
    confidence: float
    explanation: str
    nuance: str | None = None


class ClaimResult(BaseModel):
    claim: str
    category: str | None = None
    timestamp: str | None = None
    specificity: str | None = None
    verdict: str
    confidence: float
    explanation: str
    nuance: str | None = None
    sources: List[EvidenceSource] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    claims: List[ClaimResult]
    summary: str | None = None
    overall_rating: str | None = None
    took_ms: int
    warnings: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    research_service_url: str
