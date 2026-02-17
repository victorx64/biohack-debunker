from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI

from .config import Settings
from .db import create_pool
from .observability import configure_logging, metrics_response, observability_middleware
from .redis_client import create_redis
from .routers import analysis as analysis_router
from .routers import feed as feed_router
from .routers import health as health_router
from .services.analysis_queue import AnalysisQueue
from .services.orchestrator import Orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.settings = settings
    app.state.db = await create_pool(settings.database_dsn)
    app.state.redis = await create_redis(settings.redis_url)
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, read=300.0)
    )
    app.state.orchestrator = Orchestrator(app.state.http_client, settings)
    app.state.analysis_queue = AnalysisQueue(
        client=app.state.redis,
        queue_name=settings.analysis_queue_name,
        dlq_name=settings.analysis_dlq_name,
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.redis.close()
        await app.state.db.close()


app = FastAPI(title="API Gateway", version="0.1.0", lifespan=lifespan)
configure_logging("api-gateway")
app.middleware("http")(observability_middleware)

app.include_router(analysis_router.router, prefix="/api/v1")
app.include_router(feed_router.router, prefix="/api/v1")
app.include_router(health_router.router)


@app.get("/metrics")
async def metrics():
    return metrics_response()
