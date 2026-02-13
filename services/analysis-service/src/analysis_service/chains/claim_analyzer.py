from __future__ import annotations

import json
import logging
import re
from typing import List

import httpx

from ..llm_client import LLMClient, LLMUsage
from ..prompts.analysis import CLAIM_ANALYSIS_PROMPT
from ..schemas import ClaimAnalysis, EvidenceSource

logger = logging.getLogger("analysis_service.claim_analyzer")


def _normalize_verdict(value: object, has_sources: bool) -> str:
    raw = str(value or "").strip().lower()
    normalized = re.sub(r"[\s-]+", "_", raw)
    aliases = {
        "supported": "supported",
        "partially_supported": "partially_supported",
        "partial_support": "partially_supported",
        "partly_supported": "partially_supported",
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
    return _coerce_analysis(data, sources), usage


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
                    "publication_type": source.publication_type,
                    "relevance_score": source.relevance_score,
                    "abstract": source.snippet,
                },
                ensure_ascii=True,
            )
        )
    return "\n".join(items)


def _coerce_analysis(data: object, sources: List[EvidenceSource]) -> ClaimAnalysis:
    if not isinstance(data, dict):
        raise RuntimeError("LLM response missing analysis fields")
    verdict = _normalize_verdict(data.get("verdict"), has_sources=bool(sources))
    confidence = float(data.get("confidence") or 0.5)
    explanation = str(data.get("explanation") or "Insufficient evidence available.").strip()
    nuance = data.get("nuance")
    evidence_level = _normalize_label(data.get("evidence_level"))
    study_type = _normalize_label(data.get("study_type"))
    if not evidence_level or not study_type:
        inferred_level, inferred_type = _infer_evidence_classification(sources)
        evidence_level = evidence_level or inferred_level
        study_type = study_type or inferred_type
    analysis = ClaimAnalysis(
        verdict=verdict,
        confidence=max(0.0, min(confidence, 1.0)),
        explanation=explanation,
        nuance=str(nuance).strip() if nuance else None,
        evidence_level=evidence_level,
        study_type=study_type,
    )
    return _apply_evidence_policy(analysis, sources)


def _normalize_label(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _infer_evidence_classification(
    sources: List[EvidenceSource],
) -> tuple[str, str]:
    best_type = "unknown"
    best_rank = 0
    for source in sources:
        study_type = _classify_source(source)
        rank = _study_type_rank(study_type)
        if rank > best_rank:
            best_rank = rank
            best_type = study_type
    return _evidence_level_for_type(best_type), best_type


def _classify_source(source: EvidenceSource) -> str:
    tags: list[str] = []
    if source.publication_type:
        tags.extend(tag.lower() for tag in source.publication_type if tag)
    if source.source_type:
        tags.append(source.source_type.lower())
    joined = " | ".join(tags)
    if "meta-analysis" in joined or "meta analysis" in joined:
        return "meta_analysis"
    if "systematic review" in joined:
        return "systematic_review"
    if "randomized controlled trial" in joined or "randomised controlled trial" in joined:
        return "rct"
    if "randomized" in joined or "randomised" in joined:
        return "rct"
    if "clinical trial" in joined:
        return "clinical_trial"
    if "cohort" in joined or "case-control" in joined or "case control" in joined:
        return "observational"
    if "cross-sectional" in joined or "observational" in joined:
        return "observational"
    if "case reports" in joined or "case report" in joined:
        return "case_report"
    if "in vitro" in joined or "cell line" in joined or "cell culture" in joined:
        return "in_vitro"
    if "animals" in joined or "animal" in joined or "rodent" in joined:
        return "animal"
    if "mice" in joined or "mouse" in joined or "rat" in joined:
        return "animal"
    return "unknown"


def _study_type_rank(study_type: str) -> int:
    return {
        "meta_analysis": 6,
        "systematic_review": 5,
        "rct": 4,
        "clinical_trial": 3,
        "observational": 2,
        "case_report": 1,
        "animal": 1,
        "in_vitro": 1,
        "unknown": 0,
    }.get(study_type, 0)


def _evidence_level_for_type(study_type: str) -> str:
    if study_type in {"meta_analysis", "systematic_review", "rct", "clinical_trial"}:
        return "high"
    if study_type == "observational":
        return "moderate"
    if study_type in {"case_report", "animal", "in_vitro"}:
        return "low"
    return "very_low"


def _has_human_evidence(sources: List[EvidenceSource]) -> bool:
    for source in sources:
        for tag in source.publication_type or []:
            if str(tag).strip().lower() == "humans":
                return True
    return False


def _apply_evidence_policy(
    analysis: ClaimAnalysis,
    sources: List[EvidenceSource],
) -> ClaimAnalysis:
    verdict = analysis.verdict
    confidence = analysis.confidence
    nuance = analysis.nuance
    evidence_level = analysis.evidence_level or "very_low"
    study_type = analysis.study_type or "unknown"

    if not sources and verdict != "no_evidence_found":
        verdict = "no_evidence_found"
        confidence = min(confidence, 0.2)

    if sources and verdict == "no_evidence_found":
        verdict = "unsupported_by_evidence"

    if evidence_level in {"low", "very_low"}:
        if verdict == "supported":
            verdict = "partially_supported"
        confidence = min(confidence, 0.55)

    if study_type in {"animal", "in_vitro"} and not _has_human_evidence(sources):
        if verdict in {"supported", "partially_supported"}:
            verdict = "unsupported_by_evidence"
        confidence = min(confidence, 0.4)
        note = "Evidence is limited to non-human or in vitro studies; human efficacy is unproven."
        if not nuance:
            nuance = note
        elif note not in nuance:
            nuance = f"{nuance} {note}".strip()

    return ClaimAnalysis(
        verdict=verdict,
        confidence=max(0.0, min(confidence, 1.0)),
        explanation=analysis.explanation,
        nuance=nuance,
        evidence_level=evidence_level,
        study_type=study_type,
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
