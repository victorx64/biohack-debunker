from __future__ import annotations

from math import ceil
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request

from ..db import count_feed, fetch_feed
from ..middleware.rate_limit import rate_limit_dependency
from ..schemas import FeedItem, FeedResponse, VideoInfo


router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("", response_model=FeedResponse)
async def get_feed(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> FeedResponse:
    settings = request.app.state.settings
    rate_limit = rate_limit_dependency(settings)
    await rate_limit(request)

    if not settings.enable_public_feed:
        raise HTTPException(status_code=404, detail="Public feed is disabled")

    pool = request.app.state.db
    total = await count_feed(pool)
    pages = max(1, ceil(total / limit)) if total else 1
    page = min(page, pages)
    offset = (page - 1) * limit

    rows = await fetch_feed(pool, limit, offset)
    items: List[FeedItem] = []
    for row in rows:
        video = None
        if row.get("youtube_video_id"):
            video = VideoInfo(
                youtube_id=row.get("youtube_video_id"),
                title=row.get("video_title"),
                channel=row.get("channel_name"),
                duration=row.get("video_duration"),
                thumbnail_url=row.get("thumbnail_url"),
            )
        items.append(
            FeedItem(
                id=row.get("id"),
                video=video,
                summary=row.get("summary"),
                overall_rating=row.get("overall_rating"),
                created_at=row.get("created_at"),
            )
        )

    return FeedResponse(items=items, total=total, page=page, pages=pages)
