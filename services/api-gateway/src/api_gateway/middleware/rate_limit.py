from __future__ import annotations

from fastapi import HTTPException, Request

from ..config import Settings


def rate_limit_dependency(settings: Settings):
    async def limiter(request: Request) -> None:
        redis = request.app.state.redis
        if redis is None:
            raise HTTPException(status_code=503, detail="Redis is not available")
        if settings.rate_limit_requests <= 0:
            return
        client = request.client.host if request.client else "anonymous"
        email = request.headers.get("x-user-email")
        identifier = email or client
        key = f"rate:{identifier}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, settings.rate_limit_window)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Rate limit error: {exc}") from exc
        if count > settings.rate_limit_requests:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return limiter
