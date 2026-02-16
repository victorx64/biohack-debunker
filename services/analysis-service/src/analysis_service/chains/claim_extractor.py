from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List

from ..llm_client import LLMClient
from ..prompts.extraction import (
    CLAIM_EXTRACTION_SYSTEM_PROMPT,
    CLAIM_EXTRACTION_USER_PROMPT,
    CLAIM_QUERY_SYSTEM_PROMPT,
    CLAIM_QUERY_USER_PROMPT,
)
from ..schemas import ClaimDraft, TranscriptSegment

logger = logging.getLogger("analysis_service.claim_extractor")
_SEARCH_QUERY_MAX_ATTEMPTS = 3


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
            extraction_system_prompt = CLAIM_EXTRACTION_SYSTEM_PROMPT.format(
                claims_per_chunk=claims_per_chunk,
            )
            extraction_payload = CLAIM_EXTRACTION_USER_PROMPT.format(
                segments_json=chunk,
            )
            extracted_data = await llm.generate_json(
                extraction_system_prompt,
                extraction_payload,
                trace={"chunk": index, "chunks_total": len(chunks)},
            )
            claims = _coerce_claims(extracted_data)
            if not claims:
                return claims

            query_payload = CLAIM_QUERY_USER_PROMPT.format(
                claims_json=_format_query_input(claims),
            )
            invalid_queries: List[str] = []
            for attempt in range(1, _SEARCH_QUERY_MAX_ATTEMPTS + 1):
                query_data = await llm.generate_json(
                    CLAIM_QUERY_SYSTEM_PROMPT,
                    query_payload,
                    trace={
                        "chunk": index,
                        "chunks_total": len(chunks),
                        "stage": "search_query",
                        "attempt": attempt,
                    },
                )
                _reset_search_queries(claims)
                _apply_search_queries(claims, query_data)
                invalid_queries = _collect_invalid_search_queries(claims)
                if not invalid_queries:
                    break
                logger.warning(
                    "invalid search_query output chunk=%s/%s attempt=%s/%s details=%s",
                    index,
                    len(chunks),
                    attempt,
                    _SEARCH_QUERY_MAX_ATTEMPTS,
                    invalid_queries,
                )
                if attempt < _SEARCH_QUERY_MAX_ATTEMPTS:
                    query_payload = _build_query_retry_payload(claims)

            if invalid_queries:
                raise RuntimeError(
                    "search_query generation failed validation after retries: "
                    + "; ".join(invalid_queries)
                )
            return claims

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
                search_query=_normalize(item.get("search_query")),
            )
        )
    return claims


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_query_input(claims: List[ClaimDraft]) -> str:
    payload = {
        "claims": [
            {
                "id": index,
                "claim": claim.claim,
                "timestamp": claim.timestamp,
            }
            for index, claim in enumerate(claims, start=1)
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def _apply_search_queries(claims: List[ClaimDraft], data: object) -> None:
    if not isinstance(data, dict):
        return
    items = data.get("claims")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, int):
            continue
        if identifier < 1 or identifier > len(claims):
            continue
        claims[identifier - 1].search_query = _normalize(item.get("search_query"))


def _reset_search_queries(claims: List[ClaimDraft]) -> None:
    for claim in claims:
        claim.search_query = None


def _build_query_retry_payload(claims: List[ClaimDraft]) -> str:
    base_payload = CLAIM_QUERY_USER_PROMPT.format(
        claims_json=_format_query_input(claims),
    )
    return (
        f"{base_payload}\n\n"
        "Previous output contained invalid or truncated `search_query` values. "
        "Regenerate complete JSON for all claims. "
        "Each search_query must be a full PubMed query with balanced parentheses and balanced quotes."
    )


def _collect_invalid_search_queries(claims: List[ClaimDraft]) -> List[str]:
    invalid: List[str] = []
    for index, claim in enumerate(claims, start=1):
        query = claim.search_query
        if not query:
            invalid.append(f"id={index}:missing")
            continue
        reason = _validate_search_query(query)
        if reason:
            invalid.append(f"id={index}:{reason}")
    return invalid


def _validate_search_query(query: str) -> str | None:
    text = query.strip()
    if len(text) < 12:
        return "too_short"

    if re.search(r"\b(?:AND|OR|NOT)\s*$", text, flags=re.IGNORECASE):
        return "dangling_operator"

    if text.endswith("("):
        return "dangling_open_paren"

    if text.count("(") != text.count(")"):
        return "unbalanced_parentheses"

    quote_count = text.count('"')
    if quote_count % 2 != 0:
        return "unbalanced_quotes"

    if text.count("[") != text.count("]"):
        return "unbalanced_brackets"

    return None


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
