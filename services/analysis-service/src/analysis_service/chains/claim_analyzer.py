from __future__ import annotations

import json
from typing import List

import httpx

from ..llm_client import LLMClient
from ..prompts.analysis import CLAIM_ANALYSIS_PROMPT
from ..schemas import ClaimAnalysis, EvidenceSource


async def analyze_claim(
    claim: str,
    sources: List[EvidenceSource],
    llm: LLMClient,
) -> ClaimAnalysis:
    if llm.enabled:
        try:
            evidence = _format_evidence(sources)
            prompt = CLAIM_ANALYSIS_PROMPT.format(claim=claim, evidence=evidence)
            data = await llm.generate_json("Claim analysis", prompt)
            return _coerce_analysis(data)
        except Exception:
            pass
    return _stub_analysis(sources)


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
        return _stub_analysis([])
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


def _stub_analysis(sources: List[EvidenceSource]) -> ClaimAnalysis:
    if not sources:
        return ClaimAnalysis(
            verdict="unsupported",
            confidence=0.35,
            explanation="No research sources were available to support this claim.",
            nuance="Evidence may exist, but it was not retrieved.",
        )
    return ClaimAnalysis(
        verdict="partially_supported",
        confidence=0.6,
        explanation="Some evidence sources relate to this claim, but strength and relevance vary.",
        nuance="Treat as preliminary until higher-quality evidence is reviewed.",
    )


async def fetch_research(
    client: httpx.AsyncClient,
    research_url: str,
    claim: str,
    max_results: int,
    sources: List[str],
) -> List[EvidenceSource]:
    payload = {"query": claim, "max_results": max_results, "sources": sources}
    response = await client.post(research_url, json=payload)
    response.raise_for_status()
    data = response.json()
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
