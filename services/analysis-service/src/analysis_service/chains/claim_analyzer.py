from __future__ import annotations

import json
import logging
import re
from typing import List

import httpx

from ..llm_client import LLMClient, LLMUsage
from ..prompts.analysis import CLAIM_ANALYSIS_SYSTEM_PROMPT, CLAIM_ANALYSIS_USER_PROMPT
from ..schemas import ClaimAnalysis, EvidenceSource

logger = logging.getLogger("analysis_service.claim_analyzer")


def _normalize_verdict(value: object, has_sources: bool) -> str:
    raw = str(value or "").strip().lower()
    normalized = re.sub(r"[\s-]+", "_", raw)
    aliases = {
        "supported": "supported",
        "unsupported": "unsupported_by_evidence",
        "not_supported": "unsupported_by_evidence",
        "insufficient_evidence": "unsupported_by_evidence",
        "unsupported_by_evidence": "unsupported_by_evidence",
        "no_evidence": "no_evidence_found",
        "no_evidence_found": "no_evidence_found",
        "no_supporting_evidence": "no_evidence_found",
    }
    mapped = aliases.get(normalized)
    if mapped:
        if mapped == "unsupported_by_evidence" and not has_sources:
            return "no_evidence_found"
        return mapped
    return "unsupported_by_evidence" if has_sources else "no_evidence_found"


async def analyze_claim(
    claim: str,
    sources: List[EvidenceSource],
    llm: LLMClient,
    claim_index: int | None = None,
    claims_total: int | None = None,
) -> tuple[ClaimAnalysis, LLMUsage]:
    if not llm.enabled:
        raise RuntimeError("LLM client is not configured")
    logger.info("analyzing claim claim=%s sources=%s", claim[:120], len(sources))
    input_json = _format_prompt_input(claim, sources)
    prompt = CLAIM_ANALYSIS_USER_PROMPT.format(input_json=input_json)
    data, usage = await llm.generate_json_with_usage(
        CLAIM_ANALYSIS_SYSTEM_PROMPT,
        prompt,
        trace={
            "claim_index": claim_index,
            "claims_total": claims_total,
            "claim_preview": claim[:120],
        },
    )
    return _coerce_analysis(data, sources), usage


def _format_evidence(sources: List[EvidenceSource]) -> str:
    if not sources:
        return "[]"
    items = []
    for source in sources:
        items.append(
            {
                "title": source.title,
                "url": source.url,
                "source_type": source.source_type,
                "publication_type": source.publication_type,
                "relevance_score": source.relevance_score,
                "snippet": source.snippet,
            }
        )
    return json.dumps(items, ensure_ascii=False)


def _format_prompt_input(claim: str, sources: List[EvidenceSource]) -> str:
    payload = {
        "claim": claim,
        "evidence": json.loads(_format_evidence(sources)),
    }
    return json.dumps(payload, ensure_ascii=False)


def _coerce_analysis(data: object, sources: List[EvidenceSource]) -> ClaimAnalysis:
    if not isinstance(data, dict):
        raise RuntimeError("LLM response missing analysis fields")
    verdict = _normalize_verdict(data.get("verdict"), has_sources=bool(sources))
    confidence = float(data.get("confidence") or 0.5)
    explanation = str(data.get("explanation") or "Insufficient evidence available.").strip()
    nuance = data.get("nuance")
    analysis = ClaimAnalysis(
        verdict=verdict,
        confidence=max(0.0, min(confidence, 1.0)),
        explanation=explanation,
        nuance=str(nuance).strip() if nuance else None,
    )
    return _apply_evidence_policy(analysis, sources)


def _apply_evidence_policy(
    analysis: ClaimAnalysis,
    sources: List[EvidenceSource],
) -> ClaimAnalysis:
    verdict = analysis.verdict
    confidence = analysis.confidence
    nuance = analysis.nuance

    if not sources and verdict != "no_evidence_found":
        verdict = "no_evidence_found"
        confidence = min(confidence, 0.2)

    if sources and verdict == "no_evidence_found":
        verdict = "unsupported_by_evidence"

    return ClaimAnalysis(
        verdict=verdict,
        confidence=max(0.0, min(confidence, 1.0)),
        explanation=analysis.explanation,
        nuance=nuance,
    )


async def fetch_research(
    client: httpx.AsyncClient,
    research_url: str,
    claim: str,
    search_query: str | None,
    max_results: int,
    sources: List[str],
) -> tuple[List[EvidenceSource], dict[str, int]]:
    query = search_query or claim
    payload = {
        "query": query,
        "max_results": max_results,
        "sources": sources,
    }
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
                publication_type=item.get("publication_type"),
                relevance_score=float(item.get("relevance_score") or 0.0),
                snippet=item.get("snippet"),
            )
        )
    usage = {
        "pubmed_requests": int(data.get("pubmed_requests") or 0),
    }
    return results, usage
