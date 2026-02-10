from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

import httpx

from ..config import Settings
from ..db import ClaimInsert, update_analysis_status, update_results, update_transcription, insert_claims_and_sources
from ..schemas import AnalysisCreateRequest


class Orchestrator:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = http_client
        self._settings = settings

    async def run_analysis(
        self,
        pool,
        analysis_id: UUID,
        request: AnalysisCreateRequest,
    ) -> None:
        await update_analysis_status(pool, analysis_id, "processing")
        try:
            transcription = await self._fetch_transcription(request.youtube_url)
            await update_transcription(
                pool,
                analysis_id,
                transcription["transcript"],
                transcription["video"],
            )

            analysis = await self._fetch_analysis(
                transcription["transcript"],
                request,
            )
            claims = self._map_claims(analysis.get("claims", []))
            await insert_claims_and_sources(pool, analysis_id, claims)
            completed_at = datetime.utcnow()
            await update_results(
                pool,
                analysis_id,
                analysis.get("summary"),
                analysis.get("overall_rating"),
                completed_at,
            )
        except Exception:
            await update_analysis_status(pool, analysis_id, "failed")
            raise

    async def _fetch_transcription(self, youtube_url: str) -> dict:
        url = f"{self._settings.transcription_service_url.rstrip('/')}/transcription"
        response = await self._client.post(url, json={"youtube_url": youtube_url})
        response.raise_for_status()
        return response.json()

    async def _fetch_analysis(self, transcript: str, request: AnalysisCreateRequest) -> dict:
        url = f"{self._settings.analysis_service_url.rstrip('/')}/analyze"
        payload = {
            "transcript": transcript,
            "claims_per_chunk": request.claims_per_chunk,
            "chunk_size_chars": request.chunk_size_chars,
            "research_max_results": request.research_max_results,
            "research_sources": request.research_sources,
        }
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data

    def _map_claims(self, claims: List[dict]) -> List[ClaimInsert]:
        mapped: List[ClaimInsert] = []
        for claim in claims:
            mapped.append(
                ClaimInsert(
                    claim=str(claim.get("claim") or ""),
                    category=claim.get("category"),
                    timestamp=claim.get("timestamp"),
                    verdict=claim.get("verdict"),
                    confidence=claim.get("confidence"),
                    explanation=claim.get("explanation"),
                    sources=claim.get("sources") or [],
                )
            )
        return mapped
