from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import List

import httpx
import redis.asyncio as redis

from .schemas import ResearchSource


logger = logging.getLogger(__name__)


class _RateLimiter:
    def __init__(self, max_rps: int) -> None:
        if max_rps <= 0:
            raise ValueError("max_rps must be > 0")
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
    _RESERVE_SLOT_SCRIPT = """
    local now_ms = tonumber(ARGV[1])
    local interval_ms = tonumber(ARGV[2])
    local ttl_ms = tonumber(ARGV[3])

    local current = redis.call('GET', KEYS[1])
    local next_allowed_ms = now_ms
    if current then
      local stored = tonumber(current)
      if stored and stored > next_allowed_ms then
        next_allowed_ms = stored
      end
    end

    local scheduled_next_ms = next_allowed_ms + interval_ms
    redis.call('PSETEX', KEYS[1], ttl_ms, tostring(scheduled_next_ms))
    return next_allowed_ms
    """

    def __init__(self, client: redis.Redis, max_rps: int, key_prefix: str = "pubmed:rps") -> None:
        if max_rps <= 0:
            raise ValueError("max_rps must be > 0")
        self._client = client
        self._max_rps = max_rps
        self._key_prefix = key_prefix
        self._interval_ms = max(1, int(1000 / max_rps))
        self._ttl_ms = max(2000, self._interval_ms * max_rps * 4)

    async def acquire(self) -> None:
        now_ms = int(time.time() * 1000)
        key = self._key_prefix
        allowed_at_ms = await self._client.eval(
            self._RESERVE_SLOT_SCRIPT,
            1,
            key,
            now_ms,
            self._interval_ms,
            self._ttl_ms,
        )
        wait_ms = int(allowed_at_ms) - now_ms
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000)


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

    def build_query(self, query: str) -> str:
        # start_year = date.today().year - 10
        # date_range = f"\"{start_year}/01/01\"[Date - Publication] : \"3000\"[Date - Publication]"

        query = query.strip()
        if not query:
            return query
        return (
            f"({query}) AND Humans[Mesh] AND english[lang]"
            # f"AND {language_filter} AND ({date_range})"
        )

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
        abstracts = await self._efetch_abstracts(ids)

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
                    publication_type=_coerce_pubtypes(item.get("pubtype")),
                    relevance_score=1.0,
                    snippet=abstracts.get(pubmed_id) or item.get("elocationid"),
                )
            )
        return results

    async def _efetch_abstracts(self, ids: List[str]) -> dict[str, str]:
        if not ids:
            return {}
        params = {
            "db": "pubmed",
            "retmode": "xml",
            "rettype": "abstract",
            "id": ",".join(ids),
        }
        try:
            xml_text = await self._get_text("efetch.fcgi", params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {}
            raise
        return _parse_abstracts_from_xml(xml_text)

    async def _get(self, path: str, params: dict[str, str]) -> dict:
        request_params = dict(params)
        if self._api_key:
            request_params["api_key"] = self._api_key

        await self._rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                response = await client.get(f"{self._base_url}/{path}", params=request_params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                retry_after = exc.response.headers.get("Retry-After")
                logger.warning(
                    "PubMed HTTP error path=%s status=%s retry_after=%s term=%r body=%r",
                    path,
                    exc.response.status_code,
                    retry_after,
                    request_params.get("term"),
                    _truncate(exc.response.text),
                )
                raise
            except httpx.TimeoutException as exc:
                logger.warning(
                    "PubMed timeout path=%s term=%r error=%s",
                    path,
                    request_params.get("term"),
                    str(exc),
                )
                raise
            except httpx.RequestError as exc:
                logger.warning(
                    "PubMed request error path=%s term=%r error_type=%s error=%s",
                    path,
                    request_params.get("term"),
                    type(exc).__name__,
                    str(exc),
                )
                raise

    async def _get_text(self, path: str, params: dict[str, str]) -> str:
        request_params = dict(params)
        if self._api_key:
            request_params["api_key"] = self._api_key

        await self._rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                response = await client.get(f"{self._base_url}/{path}", params=request_params)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as exc:
                retry_after = exc.response.headers.get("Retry-After")
                logger.warning(
                    "PubMed HTTP error path=%s status=%s retry_after=%s ids=%r body=%r",
                    path,
                    exc.response.status_code,
                    retry_after,
                    request_params.get("id"),
                    _truncate(exc.response.text),
                )
                raise
            except httpx.TimeoutException as exc:
                logger.warning(
                    "PubMed timeout path=%s ids=%r error=%s",
                    path,
                    request_params.get("id"),
                    str(exc),
                )
                raise
            except httpx.RequestError as exc:
                logger.warning(
                    "PubMed request error path=%s ids=%r error_type=%s error=%s",
                    path,
                    request_params.get("id"),
                    type(exc).__name__,
                    str(exc),
                )
                raise


def _truncate(value: str, limit: int = 500) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"


def _parse_pubdate(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"\d{4}", value)
    if not match:
        return None
    year = int(match.group(0))
    return date(year, 1, 1)


def _coerce_pubtypes(value: object) -> List[str] | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else None
    if isinstance(value, list):
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return cleaned or None
    return None


def _parse_abstracts_from_xml(xml_text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    results: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_elem = article.find(".//PMID")
        if pmid_elem is None or not pmid_elem.text:
            continue
        pmid = pmid_elem.text.strip()
        abstract_texts = []
        for node in article.findall(".//Abstract/AbstractText"):
            text = "".join(node.itertext()).strip()
            if text:
                abstract_texts.append(text)
        if abstract_texts:
            results[pmid] = "\n".join(abstract_texts)
    return results
