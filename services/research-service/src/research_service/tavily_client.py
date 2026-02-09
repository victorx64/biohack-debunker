from __future__ import annotations

from typing import List

import httpx

from .schemas import ResearchSource


class TavilyClient:
    def __init__(self, api_key: str | None, base_url: str = "https://api.tavily.com") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int) -> List[ResearchSource]:
        if not self._api_key:
            raise RuntimeError("TAVILY_API_KEY is not set")

        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self._base_url}/search", json=payload)
            response.raise_for_status()
            data = response.json()

        results: List[ResearchSource] = []
        for item in data.get("results", []):
            results.append(
                ResearchSource(
                    title=item.get("title") or "Untitled result",
                    url=item.get("url") or "",
                    source_type="tavily",
                    relevance_score=float(item.get("score", 0.0)),
                    snippet=item.get("content") or item.get("snippet"),
                )
            )
        return results
