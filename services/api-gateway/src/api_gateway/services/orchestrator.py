from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

import httpx
import logging

from ..config import Settings
from ..db import ClaimInsert, update_analysis_status, update_results, update_transcription, insert_claims_and_sources
from ..observability import correlation_headers, observe_llm_tokens, observe_pubmed_calls, set_analysis_id
from ..schemas import AnalysisCreateRequest


logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = http_client
        self._settings = settings

    async def run_analysis(
        self,
        pool,
        analysis_id: UUID,
        request: AnalysisCreateRequest,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        set_analysis_id(str(analysis_id))
        await update_analysis_status(pool, analysis_id, "processing")
        downstream_headers = correlation_headers(request_id=request_id, correlation_id=correlation_id)
        downstream_headers["X-Analysis-ID"] = str(analysis_id)

        transcription = await self._fetch_transcription(request.youtube_url, downstream_headers)
        await update_transcription(
            pool,
            analysis_id,
            transcription["transcript"],
            transcription["video"],
        )

        analysis = await self._fetch_analysis(
            transcription.get("segments") or [],
            request,
            downstream_headers,
        )
        claims = self._map_claims(analysis.get("claims", []))
        await insert_claims_and_sources(pool, analysis_id, claims)
        completed_at = datetime.utcnow()
        costs = analysis.get("costs") or {}
        observe_pubmed_calls(int(costs.get("pubmed_requests") or 0), endpoint="/analyze")
        observe_llm_tokens("prompt", int(costs.get("llm_prompt_tokens") or 0))
        observe_llm_tokens("completion", int(costs.get("llm_completion_tokens") or 0))
        observe_llm_tokens("report_prompt", int(costs.get("report_prompt_tokens") or 0))
        observe_llm_tokens("report_completion", int(costs.get("report_completion_tokens") or 0))
        await update_results(
            pool,
            analysis_id,
            analysis.get("summary"),
            analysis.get("overall_rating"),
            completed_at,
            int(costs.get("pubmed_requests") or 0),
            int(costs.get("llm_prompt_tokens") or 0),
            int(costs.get("llm_completion_tokens") or 0),
            int(costs.get("report_prompt_tokens") or 0),
            int(costs.get("report_completion_tokens") or 0),
        )
        logger.info("analysis_orchestration_completed")

    async def _fetch_transcription(self, youtube_url: str, headers: dict[str, str]) -> dict:
        url = f"{self._settings.transcription_service_url.rstrip('/')}/transcription"
        response = await self._client.post(
            url,
            json={"youtube_url": youtube_url},
            headers=headers,
            timeout=httpx.Timeout(30.0, read=self._settings.transcription_read_timeout),
        )
        response.raise_for_status()
        return response.json()

    async def _fetch_analysis(
        self,
        segments: List[dict],
        request: AnalysisCreateRequest,
        headers: dict[str, str],
    ) -> dict:
        url = f"{self._settings.analysis_service_url.rstrip('/')}/analyze"
        payload = {
            "segments": segments,
            "claims_per_chunk": request.claims_per_chunk,
            "chunk_size_chars": request.chunk_size_chars,
            "research_max_results": request.research_max_results,
            "research_sources": request.research_sources,
        }
        response = await self._client.post(
            url,
            json=payload,
            headers=headers,
            timeout=httpx.Timeout(30.0, read=self._settings.analysis_read_timeout),
        )
        response.raise_for_status()
        data = response.json()
        return data

    def _map_claims(self, claims: List[dict]) -> List[ClaimInsert]:
        mapped: List[ClaimInsert] = []
        for claim in claims:
            costs = claim.get("costs") or {}
            mapped.append(
                ClaimInsert(
                    claim=str(claim.get("claim") or ""),
                    timestamp=claim.get("timestamp"),
                    verdict=claim.get("verdict"),
                    confidence=claim.get("confidence"),
                    explanation=claim.get("explanation"),
                    search_query=claim.get("search_query"),
                    sources=claim.get("sources") or [],
                    pubmed_requests=int(costs.get("pubmed_requests") or 0),
                    llm_prompt_tokens=int(costs.get("llm_prompt_tokens") or 0),
                    llm_completion_tokens=int(costs.get("llm_completion_tokens") or 0),
                )
            )
        return mapped
