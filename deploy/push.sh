#!/bin/sh
# Copy the forwarder to a Linux server over SSH and (re)start it there. Run from the repo root on the Mac.
#   deploy/push.sh <ssh target, e.g. user@host> [ssh port]          code + UI + .env, install, (re)start
#   SWITCH=1 deploy/push.sh <target> [port]                          also stop the Mac and move the register
# The repo is private: it travels over SSH (no GitHub credentials on the server). Idempotent.
set -eu
TARGET="$1"; PORT="${2:-22}"
SSH="ssh -i $HOME/.ssh/amd_forwarder -p $PORT -o StrictHostKeyChecking=accept-new $TARGET"
RSYNC_SSH="ssh -i $HOME/.ssh/amd_forwarder -p $PORT -o StrictHostKeyChecking=accept-new"
DIR='~/forwarder'

echo "== build the UI here"
(cd frontend && npm run build >/dev/null)

echo "== copy code, UI and .env"
rsync -az --delete -e "$RSYNC_SSH" \
  --exclude .git --exclude node_modules --exclude .venv --exclude __pycache__ --exclude personal \
  --exclude backend/data --exclude '.DS_Store' \
  ./ "$TARGET:forwarder/"

echo "== install (uv) on the server"
$SSH "set -e; cd $DIR/backend; command -v uv >/dev/null || python3 -m pip install -q --user uv; \
  export PATH=\$HOME/.local/bin:\$PATH; uv sync -q --frozen --no-dev; mkdir -p data"

if [ "${SWITCH:-0}" = "1" ]; then
  echo "== switch: stop the Mac (loop and server), move the register"
  pkill -f "backend/live.sh" || true
  pkill -f "uvicorn app.main:app --port 8000" || true
  sleep 2
  sqlite3 backend/data/forwarder.db "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
  rsync -az -e "$RSYNC_SSH" backend/data/forwarder.db "$TARGET:forwarder/backend/data/forwarder.db"
fi

echo "== (re)start on the server"
$SSH "cd $DIR; export PATH=\$HOME/.local/bin:\$PATH; pkill -f 'uvicorn app.main:app --port 8000' || true; \
  pgrep -f backend/live.sh >/dev/null || (setsid nohup backend/live.sh >> backend/data/live.log 2>&1 < /dev/null &); \
  for i in \$(seq 1 30); do sleep 1; curl -s -m 1 localhost:8000/api/health && break; done"
echo
echo "== done"
