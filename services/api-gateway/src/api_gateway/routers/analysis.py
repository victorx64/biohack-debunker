from __future__ import annotations

from typing import Dict, List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from ..db import (
    fetch_analysis,
    fetch_claims,
    fetch_sources,
    format_timestamp,
    create_analysis as create_analysis_row,
    fetch_latest_analysis_by_url,
)
from ..middleware.auth import user_context_dependency
from ..middleware.rate_limit import rate_limit_dependency
from ..schemas import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisCosts,
    ClaimCosts,
    AnalysisDetailResponse,
    ClaimInfo,
    SourceInfo,
    VideoInfo,
)


router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post(
    "",
    response_model=AnalysisCreateResponse,
    status_code=202,
    dependencies=[],
)
async def create_analysis(
    payload: AnalysisCreateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> AnalysisCreateResponse:
    settings = request.app.state.settings
    rate_limit = rate_limit_dependency(settings)
    await rate_limit(request)
    user_dep = user_context_dependency(settings)
    user = await user_dep(request)

    pool = request.app.state.db
    cached = await fetch_latest_analysis_by_url(pool, payload.youtube_url)
    if cached:
        estimated_time_seconds = 0 if cached.get("status") == "completed" else 60
        return AnalysisCreateResponse(
            analysis_id=cached.get("id"),
            status=cached.get("status"),
            estimated_time_seconds=estimated_time_seconds,
            poll_url=f"/api/v1/analysis/{cached.get('id')}",
        )

    analysis_id = await create_analysis_row(
        pool,
        user.user_id,
        payload.youtube_url,
        payload.is_public,
    )

    orchestrator = request.app.state.orchestrator
    background_tasks.add_task(orchestrator.run_analysis, pool, analysis_id, payload)

    return AnalysisCreateResponse(
        analysis_id=analysis_id,
        status="pending",
        estimated_time_seconds=60,
        poll_url=f"/api/v1/analysis/{analysis_id}",
    )


@router.get(
    "/{analysis_id}",
    response_model=AnalysisDetailResponse,
)
async def get_analysis_status(
    analysis_id: UUID,
    request: Request,
) -> AnalysisDetailResponse:
    settings = request.app.state.settings
    rate_limit = rate_limit_dependency(settings)
    await rate_limit(request)

    pool = request.app.state.db
    row = await fetch_analysis(pool, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")

    video = None
    if row.get("youtube_video_id"):
        video = VideoInfo(
            youtube_id=row.get("youtube_video_id"),
            title=row.get("video_title"),
            channel=row.get("channel_name"),
            duration=row.get("video_duration"),
            thumbnail_url=row.get("thumbnail_url"),
        )

    claims: List[ClaimInfo] = []
    if row.get("status") == "completed":
        claim_rows = await fetch_claims(pool, analysis_id)
        source_rows = await fetch_sources(pool, [claim["id"] for claim in claim_rows])
        sources_by_claim: Dict[UUID, List[SourceInfo]] = {}
        for source in source_rows:
            source_info = SourceInfo(
                title=source.get("title"),
                url=source.get("url"),
                type=source.get("source_type"),
                year=source.get("publication_date").year
                if source.get("publication_date")
                else None,
                publication_type=source.get("publication_type"),
                snippet=source.get("snippet"),
                relevance_score=source.get("relevance_score"),
            )
            sources_by_claim.setdefault(source.get("claim_id"), []).append(source_info)

        for claim in claim_rows:
            claims.append(
                ClaimInfo(
                    id=claim.get("id"),
                    text=claim.get("claim_text"),
                    timestamp=format_timestamp(claim.get("timestamp_start")),
                    category=claim.get("category"),
                    search_query=claim.get("search_query"),
                    verdict=claim.get("verdict"),
                    confidence=claim.get("confidence"),
                    explanation=claim.get("explanation"),
                    evidence_level=claim.get("evidence_level"),
                    study_type=claim.get("study_type"),
                    sources=sources_by_claim.get(claim.get("id"), []),
                    costs=ClaimCosts(
                        pubmed_requests=claim.get("pubmed_requests") or 0,
                        llm_prompt_tokens=claim.get("llm_prompt_tokens") or 0,
                        llm_completion_tokens=claim.get("llm_completion_tokens") or 0,
                    ),
                )
            )

    return AnalysisDetailResponse(
        id=row.get("id"),
        status=row.get("status"),
        video=video,
        summary=row.get("summary"),
        overall_rating=row.get("overall_rating"),
        claims=claims,
        costs=AnalysisCosts(
            pubmed_requests=row.get("total_pubmed_requests") or 0,
            llm_prompt_tokens=row.get("total_llm_prompt_tokens") or 0,
            llm_completion_tokens=row.get("total_llm_completion_tokens") or 0,
            report_prompt_tokens=row.get("report_llm_prompt_tokens") or 0,
            report_completion_tokens=row.get("report_llm_completion_tokens") or 0,
        ),
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )
