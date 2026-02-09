#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${RESEARCH_BASE_URL:-http://localhost:8003}"

health_json=$(curl -sS "$BASE_URL/health")
HEALTH_JSON="$health_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["HEALTH_JSON"])
if payload.get("status") != "healthy":
    sys.exit("health status not healthy")
if payload.get("cache_ttl_seconds") is None:
    sys.exit("cache_ttl_seconds missing")
PY

request_payload='{"query":"vitamin d supplementation","max_results":3,"sources":["tavily","pubmed"]}'
response_json=$(curl -sS -X POST "$BASE_URL/research" -H "Content-Type: application/json" -d "$request_payload")

RESPONSE_JSON="$response_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["RESPONSE_JSON"])
if payload.get("cached") is True:
    sys.exit("first response should not be cached")
results = payload.get("results") or []
if not results:
    sys.exit("no results in stub mode")
if not any(item.get("source_type") == "stub" for item in results):
    sys.exit("expected stub results")
PY

cached_json=$(curl -sS -X POST "$BASE_URL/research" -H "Content-Type: application/json" -d "$request_payload")
CACHED_JSON="$cached_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["CACHED_JSON"])
if payload.get("cached") is not True:
    sys.exit("second response should be cached")
PY

echo "stub integration tests passed"
