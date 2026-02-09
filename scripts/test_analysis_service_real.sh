#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${ANALYSIS_BASE_URL:-http://localhost:8002}"
REQUIRE_REAL="${ANALYSIS_REQUIRE_REAL:-0}"

if [[ -z "${TAVILY_API_KEY:-}" && "$REQUIRE_REAL" == "1" ]]; then
  echo "TAVILY_API_KEY is required for real integration tests"
  exit 1
elif [[ -z "${TAVILY_API_KEY:-}" ]]; then
  echo "TAVILY_API_KEY not set; skipping real integration tests"
  exit 0
fi

request_payload=$(cat <<'JSON'
{
  "transcript": "Omega-3 supplementation reduces triglycerides and may improve cardiovascular outcomes.",
  "max_claims": 2,
  "research_max_results": 3,
  "research_sources": ["tavily", "pubmed"]
}
JSON
)

response_json=$(curl -sS -X POST "$BASE_URL/analyze" -H "Content-Type: application/json" -d "$request_payload")

RESPONSE_JSON="$response_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["RESPONSE_JSON"])
claims = payload.get("claims") or []
if not claims:
    sys.exit("no claims returned")

source_types = set()
for claim in claims:
    for source in claim.get("sources") or []:
        source_types.add(source.get("source_type"))

if not source_types:
    sys.exit("no evidence sources returned")
if "stub" in source_types:
    sys.exit("stub sources detected in real mode")
if not source_types.intersection({"tavily", "pubmed"}):
    sys.exit("expected tavily or pubmed sources")
PY

echo "analysis real integration tests passed"
