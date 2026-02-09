#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


def http_get_json(url: str):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        sys.exit(f"request failed: {exc}")


def http_post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        sys.exit(f"request failed: {exc}")


def main() -> int:
    base_url = os.environ.get("ANALYSIS_BASE_URL", "http://localhost:8002")

    health = http_get_json(f"{base_url}/health")
    if health.get("status") != "healthy":
        sys.exit("health status not healthy")
    if not health.get("research_service_url"):
        sys.exit("research_service_url missing")

    payload = {
        "transcript": "Vitamin D supplementation can reduce risk of respiratory infections. Regular exercise improves cardiovascular health and sleep quality.",
        "max_claims": 3,
        "research_max_results": 2,
        "research_sources": ["tavily", "pubmed"],
    }

    response = http_post_json(f"{base_url}/analyze", payload)

    claims = response.get("claims") or []
    if not claims:
        sys.exit("no claims returned")
    if response.get("summary") is None:
        sys.exit("summary missing")
    if response.get("overall_rating") is None:
        sys.exit("overall_rating missing")
    if response.get("took_ms") is None:
        sys.exit("took_ms missing")

    has_sources = False
    for claim in claims:
        verdict = claim.get("verdict")
        confidence = claim.get("confidence")
        if not verdict:
            sys.exit("claim verdict missing")
        if confidence is None or not (0.0 <= float(confidence) <= 1.0):
            sys.exit("claim confidence out of range")
        sources = claim.get("sources") or []
        if sources:
            has_sources = True

    if not has_sources:
        sys.exit("no evidence sources returned")

    print("analysis stub integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
