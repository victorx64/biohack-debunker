from __future__ import annotations

import re
from datetime import date
from typing import List

import httpx

from .schemas import ResearchSource


class PubMedClient:
    def __init__(self, base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils") -> None:
        self._base_url = base_url.rstrip("/")

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
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self._base_url}/esearch.fcgi", params=params)
            response.raise_for_status()
            data = response.json()

        return data.get("esearchresult", {}).get("idlist", [])

    async def _esummary(self, ids: List[str]) -> List[ResearchSource]:
        params = {
            "db": "pubmed",
            "retmode": "json",
            "id": ",".join(ids),
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self._base_url}/esummary.fcgi", params=params)
            response.raise_for_status()
            data = response.json()

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


def _parse_pubdate(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"\d{4}", value)
    if not match:
        return None
    year = int(match.group(0))
    return date(year, 1, 1)
