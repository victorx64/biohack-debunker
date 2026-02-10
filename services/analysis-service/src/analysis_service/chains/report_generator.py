from __future__ import annotations

import json
import logging
from typing import List

from ..llm_client import LLMClient
from ..prompts.analysis import REPORT_PROMPT
from ..schemas import ClaimResult

logger = logging.getLogger("analysis_service.report_generator")


async def generate_report(claims: List[ClaimResult], llm: LLMClient) -> tuple[str | None, str | None]:
    if not llm.enabled:
        raise RuntimeError("LLM client is not configured")
    logger.info("generating report claims=%s", len(claims))
    payload = REPORT_PROMPT.format(claims=_format_claims(claims))
    data = await llm.generate_json("Report summary", payload)
    if not isinstance(data, dict):
        raise RuntimeError("LLM response missing report fields")
    summary = _normalize(data.get("summary"))
    overall = _normalize(data.get("overall_rating"))
    logger.info("report generated summary_len=%s overall=%s", len(summary or ""), overall or "(none)")
    return summary, overall


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
