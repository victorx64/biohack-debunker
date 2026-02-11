from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any, List

import httpx
import redis.asyncio as redis

from .schemas import CountsByYear, ResearchSource


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

    def __init__(self, client: redis.Redis, max_rps: int, key_prefix: str = "openalex:rps") -> None:
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


class OpenAlexClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.openalex.org",
        max_rps: int = 100,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        if redis_client is None:
            self._rate_limiter = _RateLimiter(max_rps)
        else:
            self._rate_limiter = _RedisRateLimiter(redis_client, max_rps)

    async def search(self, query: str, max_results: int) -> List[ResearchSource]:
        if not self._api_key:
            raise RuntimeError("OPENALEX_API_KEY is not set")

        params = {
            "search": query,
            "per-page": str(max_results),
            "select": "id,title,publication_date,type,primary_location,ids,cited_by_count,fwci,"
            "citation_normalized_percentile,counts_by_year,authorships",
            "api_key": self._api_key,
        }

        await self._rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self._base_url}/works", params=params)
            response.raise_for_status()
            data = response.json()

        results: List[ResearchSource] = []
        for item in data.get("results", []):
            primary_source_display_name, primary_source_is_core = _extract_primary_source(item)
            results.append(
                ResearchSource(
                    title=_coerce_str(item.get("title")) or "Untitled result",
                    url=_extract_url(item),
                    source_type="openalex",
                    publication_date=_parse_date(item.get("publication_date")),
                    publication_type=_coerce_type(item.get("type")),
                    relevance_score=_coerce_float(item.get("relevance_score")),
                    snippet=None,
                    cited_by_count=_coerce_int(item.get("cited_by_count")),
                    fwci=_coerce_optional_float(item.get("fwci")),
                    citation_normalized_percentile=_coerce_percentile(
                        item.get("citation_normalized_percentile")
                    ),
                    primary_source_display_name=primary_source_display_name,
                    primary_source_is_core=primary_source_is_core,
                    counts_by_year=_extract_counts_by_year(item.get("counts_by_year")),
                    institution_display_names=_extract_institution_display_names(item),
                )
            )
        return results


def _coerce_str(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _coerce_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_optional_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_percentile(value: object) -> float | None:
    if isinstance(value, dict):
        return _coerce_optional_float(value.get("value"))
    return _coerce_optional_float(value)


def _coerce_type(value: object) -> List[str] | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else None
    return None


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _extract_primary_source(item: dict[str, Any]) -> tuple[str | None, bool | None]:
    primary_location = item.get("primary_location")
    if not isinstance(primary_location, dict):
        return None, None

    source = primary_location.get("source")
    if not isinstance(source, dict):
        return None, None

    display_name = _coerce_str(source.get("display_name"))
    is_core = source.get("is_core")
    if not isinstance(is_core, bool):
        is_core = None
    return display_name, is_core


def _extract_counts_by_year(value: object) -> List[CountsByYear] | None:
    if not isinstance(value, list):
        return None
    results: List[CountsByYear] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        if not isinstance(year, int):
            continue
        results.append(
            CountsByYear(
                year=year,
                cited_by_count=_coerce_int(item.get("cited_by_count")) or 0,
                works_count=_coerce_int(item.get("works_count")) or 0,
            )
        )
    return results or None


def _extract_institution_display_names(item: dict[str, Any]) -> List[str] | None:
    authorships = item.get("authorships")
    if not isinstance(authorships, list):
        return None

    names: set[str] = set()
    for authorship in authorships:
        if not isinstance(authorship, dict):
            continue
        institutions = authorship.get("institutions")
        if not isinstance(institutions, list):
            continue
        for institution in institutions:
            if not isinstance(institution, dict):
                continue
            display_name = _coerce_str(institution.get("display_name"))
            if display_name:
                names.add(display_name)

    if not names:
        return None
    return sorted(names)


def _extract_url(item: dict[str, Any]) -> str:
    primary_location = item.get("primary_location")
    if isinstance(primary_location, dict):
        landing_page = primary_location.get("landing_page_url")
        if isinstance(landing_page, str) and landing_page.strip():
            return landing_page

    ids = item.get("ids")
    if isinstance(ids, dict):
        doi = ids.get("doi")
        if isinstance(doi, str) and doi.strip():
            return doi

    fallback = item.get("id")
    if isinstance(fallback, str) and fallback.strip():
        return fallback

    return ""
