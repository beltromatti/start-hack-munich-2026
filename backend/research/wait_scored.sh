#!/bin/sh
# Waits (read-only, one GET on /v1/board/me every 45 s) until a request has a verdict, then pulls the round log.
# Usage: FIVEU_BASE_URL=... FIVEU_API_KEY=... backend/research/wait_scored.sh [known_scored] [max_minutes]
cd "$(dirname "$0")/.." || exit 1
known="${1:-0}"; max="${2:-40}"; end=$(( $(date +%s) + max * 60 ))
while [ "$(date +%s)" -lt "$end" ]; do
  n=$(curl -s -m 15 -H "X-API-Key: $FIVEU_API_KEY" "$FIVEU_BASE_URL/v1/board/me" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin).get("requests", [])
    print(sum(1 for x in r if x.get("verdict") not in ("open", "pending", None)))
except Exception:
    print(-1)')
  if [ "$n" -gt "$known" ]; then break; fi
  sleep 45
done
echo "scored requests: $n (known before: $known) at $(date +%H:%M:%S)"
DB_PATH=:memory: LLM_API_KEY= LLM_BASE_URL= uv run python -m research.rounds
