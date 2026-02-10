from __future__ import annotations

import logging
from typing import List

from ..llm_client import LLMClient
from ..prompts.extraction import CLAIM_EXTRACTION_PROMPT
from ..schemas import ClaimDraft

logger = logging.getLogger("analysis_service.claim_extractor")


async def extract_claims(
    transcript: str,
    claims_per_chunk: int,
    chunk_size_chars: int,
    llm: LLMClient,
) -> List[ClaimDraft]:
    if not llm.enabled:
        raise RuntimeError("LLM client is not configured")
    logger.info(
        "extracting claims transcript_len=%s per_chunk_limit=%s chunk_size_chars=%s",
        len(transcript),
        claims_per_chunk,
        chunk_size_chars,
    )
    chunks = _chunk_transcript(transcript, chunk_size_chars)
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
            )
        )
    return claims


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chunk_transcript(text: str, limit: int = 5000) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + limit, length)
        if end < length:
            split_at = text.rfind(" ", start, end)
            if split_at > start + 200:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    logger.info("transcript chunked original_len=%s chunks=%s limit=%s", len(text), len(chunks), limit)
    return chunks
