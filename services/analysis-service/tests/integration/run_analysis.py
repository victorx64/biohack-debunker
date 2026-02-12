#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
import time


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


def wait_for_service(base_url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    health_url = f"{base_url.rstrip('/')}/health"
    while time.time() < deadline:
        try:
            http_get_json(health_url)
            return
        except SystemExit:
            time.sleep(0.5)
    sys.exit("analysis service not ready")


def main() -> int:
    base_url = os.environ.get("ANALYSIS_BASE_URL", "http://localhost:8002")

    wait_for_service(base_url)

    payload = {
        "segments": [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "Omega-3 supplementation reduces triglycerides and may improve cardiovascular outcomes.",
            }
        ],
        "claims_per_chunk": 2,
        "research_max_results": 3,
        "research_sources": ["pubmed"],
    }

    response = http_post_json(f"{base_url}/analyze", payload)

    claims = response.get("claims") or []
    if not claims:
        sys.exit("no claims returned")

    source_types = set()
    for claim in claims:
        for source in claim.get("sources") or []:
            source_types.add(source.get("source_type"))

    if not source_types:
        sys.exit("no evidence sources returned")
    if not source_types.intersection({"pubmed"}):
        sys.exit("expected pubmed sources")

    print("analysis integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
