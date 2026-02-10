from __future__ import annotations

import redis.asyncio as redis


async def create_redis(url: str) -> redis.Redis:
    client = redis.from_url(url, decode_responses=True)
    await client.ping()
    return client
