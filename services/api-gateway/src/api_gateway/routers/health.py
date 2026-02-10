from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Request

from ..schemas import HealthResponse


router = APIRouter(tags=["health"])


async def _check_service(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url, timeout=5.0)
        if response.status_code == 200:
            return "up"
    except Exception:
        return "down"
    return "down"


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    pool = request.app.state.db
    redis = request.app.state.redis
    client = request.app.state.http_client
    settings = request.app.state.settings

    services = {"database": "down", "redis": "down"}

    try:
        await pool.fetchval("SELECT 1")
        services["database"] = "up"
    except Exception:
        services["database"] = "down"

    try:
        await redis.ping()
        services["redis"] = "up"
    except Exception:
        services["redis"] = "down"

    checks = await asyncio.gather(
        _check_service(
            client,
            f"{settings.transcription_service_url.rstrip('/')}/health",
        ),
        _check_service(
            client,
            f"{settings.analysis_service_url.rstrip('/')}/health",
        ),
        return_exceptions=True,
    )
    services["transcription_service"] = "up" if checks[0] == "up" else "down"
    services["analysis_service"] = "up" if checks[1] == "up" else "down"

    status = "healthy" if all(value == "up" for value in services.values()) else "degraded"
    return HealthResponse(status=status, services=services)
