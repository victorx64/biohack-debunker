from __future__ import annotations

import re
from typing import List

from ..llm_client import LLMClient
from ..prompts.extraction import CLAIM_EXTRACTION_PROMPT
from ..schemas import ClaimDraft


_HEALTH_KEYWORDS = re.compile(
    r"\b(supplement|vitamin|diet|nutrition|exercise|sleep|longevity|risk|reduce|increase|"
    r"prevent|cause|boost|lower|raise|improve|cure|treat)\b",
    re.IGNORECASE,
)


async def extract_claims(transcript: str, max_claims: int, llm: LLMClient) -> List[ClaimDraft]:
    if llm.enabled:
        try:
            payload = CLAIM_EXTRACTION_PROMPT.format(transcript=_trim(transcript))
            data = await llm.generate_json("Claim extraction", payload)
            claims = _coerce_claims(data)
            return claims[:max_claims]
        except Exception:
            pass
    return _stub_claims(transcript, max_claims)


def _stub_claims(transcript: str, max_claims: int) -> List[ClaimDraft]:
    sentences = re.split(r"(?<=[.!?])\s+", transcript)
    claims: List[ClaimDraft] = []
    for sentence in sentences:
        if _HEALTH_KEYWORDS.search(sentence):
            claim = sentence.strip()
            if len(claim) < 10:
                continue
            claims.append(ClaimDraft(claim=claim, specificity="vague"))
        if len(claims) >= max_claims:
            break
    if not claims:
        claims.append(ClaimDraft(claim="No explicit health claims detected.", specificity="vague"))
    return claims


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
    return text[:limit] + "..."
