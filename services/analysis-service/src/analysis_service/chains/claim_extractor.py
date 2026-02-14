from __future__ import annotations

import asyncio
import json
import logging
from typing import List

from ..llm_client import LLMClient
from ..prompts.extraction import (
    CLAIM_EXTRACTION_SYSTEM_PROMPT,
    CLAIM_EXTRACTION_USER_PROMPT,
)
from ..schemas import ClaimDraft, TranscriptSegment

logger = logging.getLogger("analysis_service.claim_extractor")


async def extract_claims(
    segments: List[TranscriptSegment],
    claims_per_chunk: int,
    chunk_size_chars: int,
    llm: LLMClient,
) -> List[ClaimDraft]:
    if not llm.enabled:
        raise RuntimeError("LLM client is not configured")
    logger.info(
        "extracting claims segments=%s per_chunk_limit=%s chunk_size_chars=%s",
        len(segments),
        claims_per_chunk,
        chunk_size_chars,
    )
    if not segments:
        raise RuntimeError("Transcript segments are required for claim extraction")
    chunks = _chunk_segments(segments, chunk_size_chars)
    collected: List[ClaimDraft] = []
    seen: set[str] = set()
    semaphore = asyncio.Semaphore(10)

    async def _extract_chunk(index: int, chunk: str) -> List[ClaimDraft]:
        async with semaphore:
            system_prompt = CLAIM_EXTRACTION_SYSTEM_PROMPT.format(
                claims_per_chunk=claims_per_chunk,
            )
            payload = CLAIM_EXTRACTION_USER_PROMPT.format(
                segments_json=chunk,
            )
            data = await llm.generate_json(
                system_prompt,
                payload,
                trace={"chunk": index, "chunks_total": len(chunks)},
            )
            return _coerce_claims(data)

    tasks = [
        _extract_chunk(index, chunk)
        for index, chunk in enumerate(chunks, start=1)
    ]
    results = await asyncio.gather(*tasks)

    for index, claims in enumerate(results, start=1):
        added = 0
        for claim in claims:
            key = claim.claim.casefold()
            if key in seen:
                continue
            seen.add(key)
            collected.append(claim)
            added += 1
        logger.info(
            "claims extracted chunk=%s/%s raw=%s added=%s total=%s",
            index,
            len(chunks),
            len(claims),
            added,
            len(collected),
        )
    return collected


def _coerce_claims(data: object) -> List[ClaimDraft]:
    if isinstance(data, dict):
        data = data.get("claims")
    if not isinstance(data, list):
        return []
    claims: List[ClaimDraft] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        claims.append(
            ClaimDraft(
                claim=claim,
                timestamp=_normalize(item.get("timestamp")),
                specificity=_normalize(item.get("specificity")),
                search_query=_normalize(item.get("search_query")),
            )
        )
    return claims


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chunk_segments(segments: List[TranscriptSegment], limit: int = 5000) -> List[str]:
    if not segments:
        return []
    chunks: List[str] = []
    current: List[dict[str, str]] = []

    def _serialize(items: List[dict[str, str]]) -> str:
        return json.dumps(items, ensure_ascii=False)

    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        timestamp = _format_timestamp(segment.start)
        item = {"timestamp": timestamp, "text": text}
        candidate = current + [item]
        candidate_len = len(_serialize(candidate))

        if current and candidate_len > limit:
            chunks.append(_serialize(current))
            current = []

        if len(_serialize([item])) > limit:
            chunks.append(_serialize([item]))
            continue

        current.append(item)

    if current:
        chunks.append(_serialize(current))
    logger.info(
        "transcript segments chunked segments=%s chunks=%s limit=%s",
        len(segments),
        len(chunks),
        limit,
    )
    return chunks


def _format_timestamp(value: float) -> str:
    seconds = max(0, int(value))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
