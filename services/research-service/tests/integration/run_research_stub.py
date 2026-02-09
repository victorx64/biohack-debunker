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
    base_url = os.environ.get("RESEARCH_BASE_URL", "http://localhost:8003")

    health = http_get_json(f"{base_url}/health")
    if health.get("status") != "healthy":
        sys.exit("health status not healthy")
    if health.get("cache_ttl_seconds") is None:
        sys.exit("cache_ttl_seconds missing")

    payload = {
        "query": "vitamin d supplementation",
        "max_results": 3,
        "sources": ["tavily", "pubmed"],
    }

    response = http_post_json(f"{base_url}/research", payload)

    if response.get("cached") is True:
        sys.exit("first response should not be cached")
    results = response.get("results") or []
    if not results:
        sys.exit("no results in stub mode")
    if not any(item.get("source_type") == "stub" for item in results):
        sys.exit("expected stub results")

    cached = http_post_json(f"{base_url}/research", payload)
    if cached.get("cached") is not True:
        sys.exit("second response should be cached")

    print("stub integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
