from __future__ import annotations

from datetime import date
from typing import Any, List

import httpx

from .schemas import CountsByYear, ResearchSource


class OpenAlexClient:
    def __init__(self, api_key: str | None, base_url: str = "https://api.openalex.org") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

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
