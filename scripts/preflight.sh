#!/usr/bin/env bash
# preflight.sh - post-deploy smoke verification.
# Used by deployment/rollback runbooks: a deploy is not done until this passes.
#
# Usage:
#   ./scripts/preflight.sh https://api.ragchatbot.example.com [API_KEY]
#
# Exit codes: 0 = healthy, 1 = degraded/failure (CI-blocking)

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
API_KEY="${2:-${ADMIN_API_KEY:-}}"
GOLDEN_QUESTION='{"message": "What is your return policy?", "conversation_id": "preflight-'"$(date +%s)"'"}'

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

check() {  # name, expected, actual
  if [[ "$2" == "$3" ]]; then
    echo -e "${GREEN}PASS${NC}  $1"
    PASS=$((PASS+1))
  else
    echo -e "${RED}FAIL${NC}  $1 (expected: $2, got: $3)"
    FAIL=$((FAIL+1))
  fi
}

echo "── Preflight against: $BASE_URL ──────────────────────────"

# 1. Liveness (kubelet contract)
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/live")
check "liveness /live" "200" "$code"

# 2. Readiness (Service-endpoint contract)
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/ready")
check "readiness /ready" "200" "$code"

# 3. Health carries the expected version
deployed_version=$(curl -sf "$BASE_URL/health" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || echo "")
if [[ -n "$deployed_version" ]]; then
  echo -e "${YELLOW}INFO${NC}  deployed version: $deployed_version"
  PASS=$((PASS+1))
else
  echo -e "${RED}FAIL${NC}  /health did not report a version"
  FAIL=$((FAIL+1))
fi

# 4. Metrics exposed (Prometheus contract)
metrics=$(curl -sf "$BASE_URL/metrics" | head -c 400 || echo "")
if [[ "$metrics" == *"http"* ]]; then
  echo -e "${GREEN}PASS${NC}  /metrics serves Prometheus format"
  PASS=$((PASS+1))
else
  echo -e "${RED}FAIL${NC}  /metrics unreachable"
  FAIL=$((FAIL+1))
fi

# 5. End-to-end golden question (skipped without API key)
if [[ -n "$API_KEY" ]]; then
  answer=$(curl -s -X POST "$BASE_URL/api/v1/chat" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $API_KEY" \
    -d "$GOLDEN_QUESTION" || echo '{"error":"request failed"}')
  if echo "$answer" | python3 -c '
import sys, json
body = json.load(sys.stdin)
msg = body.get("response") or body.get("answer") or ""
sys.exit(0 if len(msg) > 20 else 1)' 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}  golden question answered"
    PASS=$((PASS+1))
  else
    echo -e "${RED}FAIL${NC}  golden question did not produce an answer"
    echo "  response head: $(echo "$answer" | head -c 200)"
    FAIL=$((FAIL+1))
  fi
else
  echo -e "${YELLOW}SKIP${NC}  golden question (no API key provided)"
fi

echo "──────────────────────────────────────────────────────────"
echo "Result: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] || exit 1
