from __future__ import annotations

import logging
from typing import List

from ..llm_client import LLMClient
from ..prompts.extraction import CLAIM_EXTRACTION_PROMPT
from ..schemas import ClaimDraft

logger = logging.getLogger("analysis_service.claim_extractor")


async def extract_claims(transcript: str, max_claims: int, llm: LLMClient) -> List[ClaimDraft]:
    if not llm.enabled:
        raise RuntimeError("LLM client is not configured")
    logger.info("extracting claims transcript_len=%s max_claims=%s", len(transcript), max_claims)
    payload = CLAIM_EXTRACTION_PROMPT.format(transcript=_trim(transcript))
    data = await llm.generate_json("Claim extraction", payload)
    claims = _coerce_claims(data)
    logger.info("claims extracted raw=%s returned=%s", len(claims), min(len(claims), max_claims))
    return claims[:max_claims]


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


def _trim(text: str, limit: int = 5000) -> str:
    if len(text) <= limit:
        return text
    logger.warning("transcript trimmed original_len=%s limit=%s", len(text), limit)
    return text[:limit] + "..."
