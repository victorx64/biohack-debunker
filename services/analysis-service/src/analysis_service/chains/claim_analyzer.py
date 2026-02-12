from __future__ import annotations

import json
import logging
from typing import List

import httpx

from ..llm_client import LLMClient, LLMUsage
from ..prompts.analysis import CLAIM_ANALYSIS_PROMPT
from ..schemas import ClaimAnalysis, EvidenceSource

logger = logging.getLogger("analysis_service.claim_analyzer")


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
    evidence = _format_evidence(sources)
    prompt = CLAIM_ANALYSIS_PROMPT.format(claim=claim, evidence=evidence)
    data, usage = await llm.generate_json_with_usage(
        "Claim analysis",
        prompt,
        trace={
            "claim_index": claim_index,
            "claims_total": claims_total,
            "claim_preview": claim[:120],
        },
        openai_reasoning={"effort": "none"},
    )
    return _coerce_analysis(data), usage


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
                    # "source_type": source.source_type,
                    "publication_type": source.publication_type,
                    # "relevance_score": source.relevance_score,
                    "abstract": source.snippet,
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
