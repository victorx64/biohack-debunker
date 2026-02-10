from __future__ import annotations

import asyncio
import re
import time
from datetime import date
from typing import List

import httpx
import redis.asyncio as redis

from .schemas import ResearchSource


class _RateLimiter:
    def __init__(self, max_rps: int) -> None:
        self._min_interval = 1.0 / max_rps
        self._lock = asyncio.Lock()
        self._next_time = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._next_time:
                await asyncio.sleep(self._next_time - now)
                now = time.monotonic()
            self._next_time = max(now, self._next_time) + self._min_interval


class _RedisRateLimiter:
    _INCR_EXPIRE_SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return current
    """

    def __init__(self, client: redis.Redis, max_rps: int, key_prefix: str = "pubmed:rps") -> None:
        self._client = client
        self._max_rps = max_rps
        self._key_prefix = key_prefix
        self._ttl_seconds = 2

    async def acquire(self) -> None:
        while True:
            now = time.time()
            window = int(now)
            key = f"{self._key_prefix}:{window}"
            current = await self._client.eval(self._INCR_EXPIRE_SCRIPT, 1, key, self._ttl_seconds)
            if int(current) <= self._max_rps:
                return
            sleep_for = (window + 1) - now
            if sleep_for < 0.01:
                sleep_for = 0.01
            await asyncio.sleep(sleep_for)


class PubMedClient:
    def __init__(
        self,
        base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        api_key: str | None = None,
        max_rps: int = 10,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        if redis_client is None:
            self._rate_limiter = _RateLimiter(max_rps)
        else:
            self._rate_limiter = _RedisRateLimiter(redis_client, max_rps)

    async def search(self, query: str, max_results: int) -> List[ResearchSource]:
        ids = await self._esearch(query, max_results)
        if not ids:
            return []
        return await self._esummary(ids)

    async def _esearch(self, query: str, max_results: int) -> List[str]:
        params = {
            "db": "pubmed",
            "retmode": "json",
            "retmax": str(max_results),
            "term": query,
        }
        data = await self._get("esearch.fcgi", params)

        return data.get("esearchresult", {}).get("idlist", [])

    async def _esummary(self, ids: List[str]) -> List[ResearchSource]:
        params = {
            "db": "pubmed",
            "retmode": "json",
            "id": ",".join(ids),
        }
        data = await self._get("esummary.fcgi", params)

        results: List[ResearchSource] = []
        summary = data.get("result", {})
        for pubmed_id in ids:
            item = summary.get(pubmed_id)
            if not item:
                continue
            results.append(
                ResearchSource(
                    title=item.get("title") or "Untitled result",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                    source_type="pubmed",
                    publication_date=_parse_pubdate(item.get("pubdate")),
                    relevance_score=1.0,
                    snippet=item.get("elocationid"),
                )
            )
        return results

    async def _get(self, path: str, params: dict[str, str]) -> dict:
        request_params = dict(params)
        if self._api_key:
            request_params["api_key"] = self._api_key

        await self._rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self._base_url}/{path}", params=request_params)
            response.raise_for_status()
            return response.json()


def _parse_pubdate(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"\d{4}", value)
    if not match:
        return None
    year = int(match.group(0))
    return date(year, 1, 1)
