#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${ANALYSIS_BASE_URL:-http://localhost:8002}"

health_json=$(curl -sS "$BASE_URL/health")
HEALTH_JSON="$health_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["HEALTH_JSON"])
if payload.get("status") != "healthy":
    sys.exit("health status not healthy")
if not payload.get("research_service_url"):
    sys.exit("research_service_url missing")
PY

request_payload=$(cat <<'JSON'
{
    "transcript": "Vitamin D supplementation can reduce risk of respiratory infections. Regular exercise improves cardiovascular health and sleep quality.",
    "max_claims": 3,
    "research_max_results": 2,
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
if payload.get("summary") is None:
    sys.exit("summary missing")
if payload.get("overall_rating") is None:
    sys.exit("overall_rating missing")
if payload.get("took_ms") is None:
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
PY

echo "analysis stub integration tests passed"
