from __future__ import annotations

import json
from typing import List

from ..llm_client import LLMClient
from ..prompts.analysis import REPORT_PROMPT
from ..schemas import ClaimResult


async def generate_report(claims: List[ClaimResult], llm: LLMClient) -> tuple[str | None, str | None]:
    if llm.enabled:
        try:
            payload = REPORT_PROMPT.format(claims=_format_claims(claims))
            data = await llm.generate_json("Report summary", payload)
            summary = _normalize(data.get("summary")) if isinstance(data, dict) else None
            overall = _normalize(data.get("overall_rating")) if isinstance(data, dict) else None
            return summary, overall
        except Exception:
            pass
    return _stub_report(claims)


def _stub_report(claims: List[ClaimResult]) -> tuple[str | None, str | None]:
    if not claims:
        return "No claims were analyzed.", "mixed"
    verdicts = [claim.verdict for claim in claims]
    summary = _basic_summary(verdicts)
    return summary, _overall_rating(verdicts)


def _basic_summary(verdicts: List[str]) -> str:
    supported = verdicts.count("supported")
    partial = verdicts.count("partially_supported")
    unsupported = verdicts.count("unsupported")
    misleading = verdicts.count("misleading")
    return (
        f"Analyzed {len(verdicts)} claims: {supported} supported, {partial} partially supported, "
        f"{unsupported} unsupported, {misleading} misleading."
    )


def _overall_rating(verdicts: List[str]) -> str:
    if not verdicts:
        return "mixed"
    negative = verdicts.count("unsupported") + verdicts.count("misleading")
    if negative == 0:
        return "accurate"
    if negative / len(verdicts) <= 0.25:
        return "mostly_accurate"
    if negative / len(verdicts) <= 0.6:
        return "mixed"
    return "misleading"


def _format_claims(claims: List[ClaimResult]) -> str:
    return "\n".join(
        json.dumps(
            {
                "claim": claim.claim,
                "verdict": claim.verdict,
                "confidence": claim.confidence,
                "explanation": claim.explanation,
            },
            ensure_ascii=True,
        )
        for claim in claims
    )


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
