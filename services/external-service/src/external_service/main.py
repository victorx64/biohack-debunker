from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, Query, Request

app = FastAPI(title="External Service", version="0.1.0")

_OPENALEX_RESPONSE_PATH = Path(__file__).with_name("open-alex-search.json")


def _load_openalex_response() -> Dict[str, Any]:
    if not _OPENALEX_RESPONSE_PATH.exists():
        return {"meta": {"count": 0, "page": 1, "per_page": 0, "db_response_time_ms": 0}, "results": []}
    return json.loads(_OPENALEX_RESPONSE_PATH.read_text(encoding="utf-8"))


_OPENALEX_RESPONSE = _load_openalex_response()


def _tavily_results(query: str, max_results: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for idx in range(1, max_results + 1):
        results.append(
            {
                "title": f"Mock Tavily result {idx} for {query}",
                "url": f"https://example.test/tavily/{idx}",
                "score": 0.9 - (idx * 0.05),
                "content": f"Mock content for {query} (result {idx}).",
            }
        )
    return results


def _pubmed_ids(max_results: int) -> List[str]:
    return [str(1000 + idx) for idx in range(1, max_results + 1)]


def _pubmed_summary(ids: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"uids": ids}
    for pubmed_id in ids:
        result[pubmed_id] = {
            "title": f"Mock PubMed title {pubmed_id}",
            "pubdate": "2020",
            "pubtype": ["Journal Article"],
            "elocationid": f"PMID:{pubmed_id}",
        }
    return result


def _openai_response(system_prompt: str) -> str:
    if "Claim extraction" in system_prompt:
        return json.dumps(
            [
                {
                    "claim": "Omega-3 supplementation reduces triglycerides.",
                    "category": "supplement",
                    "timestamp": None,
                    "specificity": "specific",
                }
            ]
        )
    if "Claim analysis" in system_prompt:
        return json.dumps(
            {
                "verdict": "partially_supported",
                "confidence": 0.62,
                "explanation": "Mock evidence suggests a possible benefit.",
                "nuance": "Mock response for tests.",
            }
        )
    if "Report summary" in system_prompt:
        return json.dumps(
            {
                "summary": "Mock summary based on provided claims.",
                "overall_rating": "mixed",
            }
        )
    return json.dumps({"summary": "Mock summary", "overall_rating": "mixed"})


@app.post("/tavily/search")
async def tavily_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = str(payload.get("query") or "")
    max_results = int(payload.get("max_results") or 3)
    return {"results": _tavily_results(query, max_results)}


@app.get("/works")
async def openalex_search(
    search: str | None = None,
    per_page: int = Query(25, alias="per-page"),
    page: int = 1,
) -> Dict[str, Any]:
    _ = search
    per_page = max(per_page, 1)
    page = max(page, 1)

    meta = dict(_OPENALEX_RESPONSE.get("meta") or {})
    results = list(_OPENALEX_RESPONSE.get("results") or [])
    start = (page - 1) * per_page
    end = start + per_page
    meta["page"] = page
    meta["per_page"] = per_page
    return {"meta": meta, "results": results[start:end]}


@app.get("/pubmed/esearch.fcgi")
async def pubmed_esearch(retmax: int = 5) -> Dict[str, Any]:
    ids = _pubmed_ids(retmax)
    return {"esearchresult": {"idlist": ids}}


@app.get("/pubmed/esummary.fcgi")
async def pubmed_esummary(id: str) -> Dict[str, Any]:
    ids = [item for item in id.split(",") if item]
    return {"result": _pubmed_summary(ids)}


@app.post("/v1/chat/completions")
async def openai_chat(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    messages = payload.get("messages") or []
    system_prompt = " ".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "system"
    )
    content = _openai_response(system_prompt)
    return {"choices": [{"message": {"content": content}}]}


@app.post("/v1/messages")
async def anthropic_messages(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    system_prompt = str(payload.get("system") or "")
    content = _openai_response(system_prompt)
    return {"content": [{"text": content}]}
