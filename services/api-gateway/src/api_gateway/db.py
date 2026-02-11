from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List
from uuid import UUID, uuid4

import asyncpg


@dataclass(frozen=True)
class ClaimInsert:
    claim: str
    category: str | None
    timestamp: str | None
    verdict: str | None
    confidence: float | None
    explanation: str | None
    keywords: list[str] | None
    sources: list
    pubmed_requests: int = 0
    tavily_requests: int = 0
    openalex_requests: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0


def _utcnow() -> datetime:
    return datetime.utcnow()


def _parse_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        parts_int = [int(part) for part in parts]
    except ValueError:
        return None
    if len(parts_int) == 2:
        minutes, seconds = parts_int
        return minutes * 60 + seconds
    hours, minutes, seconds = parts_int
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    hours = value // 3600
    minutes = (value % 3600) // 60
    seconds = value % 60
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)


async def ensure_user(pool: asyncpg.Pool, email: str, default_credits: int) -> UUID:
    row = await pool.fetchrow("SELECT id FROM users WHERE email=$1", email)
    if row:
        return row["id"]
    user_id = uuid4()
    await pool.execute(
        "INSERT INTO users (id, email, credits, created_at, updated_at) "
        "VALUES ($1, $2, $3, $4, $4)",
        user_id,
        email,
        default_credits,
        _utcnow(),
    )
    return user_id


async def try_decrement_credits(pool: asyncpg.Pool, user_id: UUID) -> bool:
    row = await pool.fetchrow(
        "UPDATE users SET credits = credits - 1, updated_at = $2 "
        "WHERE id=$1 AND credits > 0 RETURNING credits",
        user_id,
        _utcnow(),
    )
    return row is not None


async def create_analysis(
    pool: asyncpg.Pool,
    user_id: UUID,
    youtube_url: str,
    is_public: bool,
) -> UUID:
    analysis_id = uuid4()
    await pool.execute(
        "INSERT INTO analyses (id, user_id, youtube_url, status, is_public, created_at) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        analysis_id,
        user_id,
        youtube_url,
        "pending",
        is_public,
        _utcnow(),
    )
    return analysis_id


async def update_analysis_status(
    pool: asyncpg.Pool,
    analysis_id: UUID,
    status: str,
    completed_at: datetime | None = None,
) -> None:
    await pool.execute(
        "UPDATE analyses SET status=$2, completed_at=$3 WHERE id=$1",
        analysis_id,
        status,
        completed_at,
    )


async def update_transcription(
    pool: asyncpg.Pool,
    analysis_id: UUID,
    transcript: str,
    video: dict,
) -> None:
    await pool.execute(
        "UPDATE analyses "
        "SET transcript=$2, youtube_video_id=$3, video_title=$4, channel_name=$5, "
        "video_duration=$6, thumbnail_url=$7 "
        "WHERE id=$1",
        analysis_id,
        transcript,
        video.get("youtube_id"),
        video.get("title"),
        video.get("channel"),
        video.get("duration"),
        video.get("thumbnail_url"),
    )


async def update_results(
    pool: asyncpg.Pool,
    analysis_id: UUID,
    summary: str | None,
    overall_rating: str | None,
    completed_at: datetime,
    total_pubmed_requests: int,
    total_tavily_requests: int,
    total_openalex_requests: int,
    total_llm_prompt_tokens: int,
    total_llm_completion_tokens: int,
    report_llm_prompt_tokens: int,
    report_llm_completion_tokens: int,
) -> None:
    await pool.execute(
        "UPDATE analyses SET summary=$2, overall_rating=$3, status=$4, completed_at=$5, "
        "total_pubmed_requests=$6, total_tavily_requests=$7, total_openalex_requests=$8, "
        "total_llm_prompt_tokens=$9, total_llm_completion_tokens=$10, "
        "report_llm_prompt_tokens=$11, report_llm_completion_tokens=$12 WHERE id=$1",
        analysis_id,
        summary,
        overall_rating,
        "completed",
        completed_at,
        total_pubmed_requests,
        total_tavily_requests,
        total_openalex_requests,
        total_llm_prompt_tokens,
        total_llm_completion_tokens,
        report_llm_prompt_tokens,
        report_llm_completion_tokens,
    )


async def insert_claims_and_sources(
    pool: asyncpg.Pool,
    analysis_id: UUID,
    claims: Iterable[ClaimInsert],
) -> List[UUID]:
    claim_ids: List[UUID] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for claim in claims:
                claim_id = uuid4()
                timestamp_start = _parse_timestamp(claim.timestamp)
                await conn.execute(
                    "INSERT INTO claims "
                    "(id, analysis_id, claim_text, timestamp_start, category, verdict, "
                    "confidence, explanation, keywords, pubmed_requests, tavily_requests, "
                    "openalex_requests, llm_prompt_tokens, llm_completion_tokens, "
                    "created_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
                    claim_id,
                    analysis_id,
                    claim.claim,
                    timestamp_start,
                    claim.category,
                    claim.verdict,
                    claim.confidence,
                    claim.explanation,
                    claim.keywords,
                    claim.pubmed_requests,
                    claim.tavily_requests,
                    claim.openalex_requests,
                    claim.llm_prompt_tokens,
                    claim.llm_completion_tokens,
                    _utcnow(),
                )
                claim_ids.append(claim_id)

                for source in claim.sources:
                    source_id = uuid4()
                    await conn.execute(
                        "INSERT INTO sources "
                        "(id, claim_id, title, url, source_type, publication_date, "
                        "publication_type, relevance_score, snippet, cited_by_count, "
                        "fwci, citation_normalized_percentile, primary_source_display_name, "
                        "primary_source_is_core, counts_by_year, institution_display_names, "
                        "created_at) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                        "$13, $14, $15, $16, $17)",
                        source_id,
                        claim_id,
                        source.get("title"),
                        source.get("url"),
                        source.get("source_type"),
                        source.get("publication_date"),
                        source.get("publication_type"),
                        source.get("relevance_score"),
                        source.get("snippet"),
                        source.get("cited_by_count"),
                        source.get("fwci"),
                        source.get("citation_normalized_percentile"),
                        source.get("primary_source_display_name"),
                        source.get("primary_source_is_core"),
                        source.get("counts_by_year"),
                        source.get("institution_display_names"),
                        _utcnow(),
                    )
    return claim_ids


async def fetch_analysis(pool: asyncpg.Pool, analysis_id: UUID) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM analyses WHERE id=$1",
        analysis_id,
    )


async def fetch_claims(pool: asyncpg.Pool, analysis_id: UUID) -> List[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM claims WHERE analysis_id=$1 ORDER BY created_at",
        analysis_id,
    )


async def fetch_sources(
    pool: asyncpg.Pool, claim_ids: Iterable[UUID]
) -> List[asyncpg.Record]:
    claim_ids_list = list(claim_ids)
    if not claim_ids_list:
        return []
    return await pool.fetch(
        "SELECT * FROM sources WHERE claim_id = ANY($1::uuid[]) ORDER BY created_at",
        claim_ids_list,
    )


async def fetch_feed(
    pool: asyncpg.Pool,
    limit: int,
    offset: int,
) -> List[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM analyses "
        "WHERE status='completed' AND is_public=true "
        "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit,
        offset,
    )


async def count_feed(pool: asyncpg.Pool) -> int:
    row = await pool.fetchrow(
        "SELECT COUNT(*) AS total FROM analyses "
        "WHERE status='completed' AND is_public=true"
    )
    return int(row["total"]) if row else 0
