#!/bin/sh
# The production forwarder. Run on ONE machine only (make live).
# Restarts by itself; to deploy new code: pkill -f "uvicorn app.main:app --port 8000"  (kills only the server, not this loop)
cd "$(dirname "$0")"
while true; do
  WORKER=1 uv run uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port 8000
  echo "forwarder exited, restarting in 2 s"
  sleep 2
done
