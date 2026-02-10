from __future__ import annotations

import json
import logging
from typing import List

import httpx

from ..llm_client import LLMClient
from ..prompts.analysis import CLAIM_ANALYSIS_PROMPT
from ..schemas import ClaimAnalysis, EvidenceSource

logger = logging.getLogger("analysis_service.claim_analyzer")


async def analyze_claim(
    claim: str,
    sources: List[EvidenceSource],
    llm: LLMClient,
) -> ClaimAnalysis:
    if not llm.enabled:
        raise RuntimeError("LLM client is not configured")
    logger.info("analyzing claim claim=%s sources=%s", claim[:120], len(sources))
    evidence = _format_evidence(sources)
    prompt = CLAIM_ANALYSIS_PROMPT.format(claim=claim, evidence=evidence)
    data = await llm.generate_json("Claim analysis", prompt)
    return _coerce_analysis(data)


def _format_evidence(sources: List[EvidenceSource]) -> str:
    if not sources:
        return "No evidence sources provided."
    items = []
    for source in sources:
        items.append(
            json.dumps(
                {
                    "title": source.title,
                    "url": source.url,
                    "source_type": source.source_type,
                    "relevance_score": source.relevance_score,
                    "snippet": source.snippet,
                },
                ensure_ascii=True,
            )
        )
    return "\n".join(items)


def _coerce_analysis(data: object) -> ClaimAnalysis:
    if not isinstance(data, dict):
        raise RuntimeError("LLM response missing analysis fields")
    verdict = str(data.get("verdict") or "unsupported").strip()
    confidence = float(data.get("confidence") or 0.5)
    explanation = str(data.get("explanation") or "Insufficient evidence available.").strip()
    nuance = data.get("nuance")
    return ClaimAnalysis(
        verdict=verdict,
        confidence=max(0.0, min(confidence, 1.0)),
        explanation=explanation,
        nuance=str(nuance).strip() if nuance else None,
    )


async def fetch_research(
    client: httpx.AsyncClient,
    research_url: str,
    claim: str,
    max_results: int,
    sources: List[str],
) -> List[EvidenceSource]:
    payload = {"query": claim, "max_results": max_results, "sources": sources}
    try:
        response = await client.post(research_url, json=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:500]
        logger.error("research request failed status=%s body=%s", exc.response.status_code, body)
        raise
    except Exception:
        logger.exception("research request failed")
        raise
    results = []
    for item in data.get("results", []):
        results.append(
            EvidenceSource(
                title=item.get("title") or "Untitled",
                url=item.get("url") or "",
                source_type=item.get("source_type") or "unknown",
                relevance_score=float(item.get("relevance_score") or 0.0),
                snippet=item.get("snippet"),
            )
        )
    return results
