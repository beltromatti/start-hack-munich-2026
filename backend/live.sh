#!/bin/sh
# The production forwarder. Run on ONE machine only (make live).
# Restarts by itself; to deploy new code: pkill -f "bin/uvicorn app.main"  (kills only the server, not this loop)
cd "$(dirname "$0")"
while true; do
  WORKER=1 uv run uvicorn app.main:app --port 8000
  echo "forwarder exited, restarting in 2 s"
  sleep 2
done
