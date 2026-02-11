from __future__ import annotations

from datetime import date
from typing import Any, List

import httpx

from .schemas import ResearchSource


class OpenAlexClient:
    def __init__(self, api_key: str | None, base_url: str = "https://api.openalex.org") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int) -> List[ResearchSource]:
        if not self._api_key:
            raise RuntimeError("OPENALEX_API_KEY is not set")

        params = {
            "query": query,
            "count": str(max_results),
            "api_key": self._api_key,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self._base_url}/find/works", params=params)
            response.raise_for_status()
            data = response.json()

        results: List[ResearchSource] = []
        for item in data.get("results", []):
            results.append(
                ResearchSource(
                    title=_coerce_str(item.get("title")) or "Untitled result",
                    url=_extract_url(item),
                    source_type="openalex",
                    publication_date=_parse_date(item.get("publication_date")),
                    publication_type=_coerce_type(item.get("type")),
                    relevance_score=_coerce_float(item.get("score")),
                    snippet=None,
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
