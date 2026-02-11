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
        raise RuntimeError(f"request failed: {exc}") from exc


def http_post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"request failed: {exc}") from exc


def main() -> int:
    base_url = os.environ.get("RESEARCH_BASE_URL", "http://localhost:8003")
    require_real = os.environ.get("RESEARCH_REQUIRE_REAL", "0")

    if not os.environ.get("TAVILY_API_KEY") and require_real == "1":
        sys.exit("TAVILY_API_KEY is required for real integration tests")
    if not os.environ.get("TAVILY_API_KEY"):
        print("TAVILY_API_KEY not set; skipping real integration tests")
        return 0

    payload = {
        "query": "omega-3 cardiovascular outcomes",
        "max_results": 5,
        "sources": ["tavily", "pubmed", "openalex"],
    }

    try:
        response = http_post_json(f"{base_url}/research", payload)
    except RuntimeError as exc:
        if require_real == "1":
            sys.exit(str(exc))
        print(f"real integration tests skipped: {exc}")
        return 0

    results = response.get("results") or []
    if not results:
        sys.exit("no results in real mode")
    if not any(item.get("source_type") in {"tavily", "pubmed", "openalex"} for item in results):
        sys.exit("expected tavily, pubmed, or openalex results")

    print("research integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
