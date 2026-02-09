#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${RESEARCH_BASE_URL:-http://localhost:8003}"
REQUIRE_REAL="${RESEARCH_REQUIRE_REAL:-0}"

if [[ -z "${TAVILY_API_KEY:-}" && "$REQUIRE_REAL" == "1" ]]; then
  echo "TAVILY_API_KEY is required for real integration tests"
  exit 1
elif [[ -z "${TAVILY_API_KEY:-}" ]]; then
  echo "TAVILY_API_KEY not set; skipping real integration tests"
  exit 0
fi

request_payload='{"query":"omega-3 cardiovascular outcomes","max_results":5,"sources":["tavily","pubmed"]}'
response_json=$(curl -sS -X POST "$BASE_URL/research" -H "Content-Type: application/json" -d "$request_payload")

RESPONSE_JSON="$response_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["RESPONSE_JSON"])
results = payload.get("results") or []
if not results:
    sys.exit("no results in real mode")
if any(item.get("source_type") == "stub" for item in results):
    sys.exit("stub results detected in real mode")
if not any(item.get("source_type") in {"tavily", "pubmed"} for item in results):
    sys.exit("expected tavily or pubmed results")
PY

echo "real integration tests passed"
