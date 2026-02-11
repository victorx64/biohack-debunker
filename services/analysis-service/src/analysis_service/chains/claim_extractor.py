from __future__ import annotations

import logging
from typing import List

from ..llm_client import LLMClient
from ..prompts.extraction import CLAIM_EXTRACTION_PROMPT
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
    for index, chunk in enumerate(chunks, start=1):
        payload = CLAIM_EXTRACTION_PROMPT.format(
            transcript=chunk,
            claims_per_chunk=claims_per_chunk,
        )
        data = await llm.generate_json(
            "Claim extraction",
            payload,
            openai_reasoning={"effort": "none"},
            trace={"chunk": index, "chunks_total": len(chunks)},
        )
        claims = _coerce_claims(data)
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
                category=_normalize(item.get("category")),
                timestamp=_normalize(item.get("timestamp")),
                specificity=_normalize(item.get("specificity")),
                keywords=_normalize_keywords(item.get("keywords")),
            )
        )
    return claims


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_keywords(value: object) -> List[str] | None:
    if not isinstance(value, list):
        return None
    results: List[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(text)
        if len(results) >= 8:
            break
    return results or None


def _chunk_segments(segments: List[TranscriptSegment], limit: int = 5000) -> List[str]:
    if not segments:
        return []
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        timestamp = _format_timestamp(segment.start)
        line = f"[{timestamp}] {text}"
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
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
