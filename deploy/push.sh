#!/bin/sh
# Move the forwarder between the Mac and a Linux server over SSH. Run from the repo root on the Mac.
# Only one machine may run the forwarder (two would answer every mail twice), so the modes are explicit:
#   deploy/push.sh <user@host> [port]           copy code + UI + .env. If the server is not live yet, it serves the
#                                               UI on a snapshot of the register with NO forwarder (a preview).
#                                               If the server is already live, it reloads the new code there.
#   SWITCH=1 deploy/push.sh <user@host> [port]  stop the Mac, move the register, start the forwarder on the server.
#   BACK=1 deploy/push.sh <user@host> [port]    the reverse: stop the server, bring the register home, start the Mac.
# The forwarder always runs as backend/live.sh from the repo root, so one pattern finds it on both machines.
# Patterns are written as [b]ackend/... so pkill/pgrep never match the shell that runs them.
# The repo is private: it travels over SSH (no GitHub credentials on the server). Idempotent.
set -eu
TARGET="$1"; PORT="${2:-22}"
OPTS="-i $HOME/.ssh/amd_forwarder -p $PORT -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15"
SSH="ssh $OPTS $TARGET"
DB=backend/data/forwarder.db
AT='cd ~/forwarder; export PATH=$HOME/.local/bin:$PATH'
LOOP='[b]ackend/live.sh'
SERVER='[u]vicorn app.main:app'
STOP="pkill -f '$LOOP' || true; pkill -f '$SERVER' || true; sleep 2"
FRESH_DB="rm -f $DB-wal $DB-shm"
HEALTH='for i in $(seq 1 40); do sleep 1; curl -s -m 1 localhost:8000/api/health && exit 0; done; echo "no health"; tail -20 backend/data/*.log; exit 1'
CHECKPOINT="python3 -c \"import sqlite3; sqlite3.connect('$DB').execute('PRAGMA wal_checkpoint(TRUNCATE)')\""

stop_mac() {
  pkill -f "$LOOP" || true
  pkill -f "[u]vicorn app.main:app --port 8000" || true
  sleep 2
  sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null
}

if [ "${BACK:-0}" = "1" ]; then
  echo "== back: stop the server, bring the register home, start the Mac"
  $SSH "$AT; $STOP; $CHECKPOINT"
  stop_mac
  rm -f "$DB-wal" "$DB-shm"
  rsync -az -e "ssh $OPTS" "$TARGET:forwarder/$DB" "$DB"
  (nohup caffeinate -is backend/live.sh >> backend/data/live.log 2>&1 < /dev/null &)
  sleep 8; curl -s localhost:8000/api/health; echo; echo "== the Mac is live again"
  exit 0
fi

echo "== build the UI here"
(cd frontend && npm run build >/dev/null)

echo "== copy code, UI and .env"
rsync -az --delete -e "ssh $OPTS" \
  --exclude .git --exclude node_modules --exclude .venv --exclude __pycache__ --exclude personal \
  --exclude backend/data --exclude '.DS_Store' \
  ./ "$TARGET:forwarder/"

echo "== install (uv) on the server"
$SSH "set -e; $AT; mkdir -p backend/data; command -v uv >/dev/null || python3 -m pip install -q --user uv \
  || python3 -m pip install -q --user --break-system-packages uv; cd backend; uv sync -q --frozen --no-dev"

LIVE=$($SSH "pgrep -f '$LOOP' >/dev/null && echo yes || echo no")

if [ "${SWITCH:-0}" = "1" ]; then
  echo "== switch: stop the Mac, move the register, start the forwarder on the server"
  $SSH "$AT; $STOP; $FRESH_DB"
  stop_mac
  rsync -az -e "ssh $OPTS" "$DB" "$TARGET:forwarder/$DB"
  $SSH "$AT; (HOST=\${HOST:-127.0.0.1} setsid nohup backend/live.sh >> backend/data/live.log 2>&1 < /dev/null &); $HEALTH"
  echo; echo "== the server is live; the Mac forwarder is stopped"
elif [ "$LIVE" = "yes" ]; then
  echo "== the server is live: reload the code (live.sh restarts uvicorn)"
  $SSH "$AT; pkill -f '$SERVER' || true; $HEALTH"
else
  echo "== preview: a snapshot of the register, UI and API only, no forwarder"
  SNAP="$(mktemp -t forwarder).db"
  sqlite3 "$DB" ".backup $SNAP"
  $SSH "$AT; $STOP; $FRESH_DB"
  rsync -az -e "ssh $OPTS" "$SNAP" "$TARGET:forwarder/$DB"
  rm -f "$SNAP"
  $SSH "$AT; cd backend; (WORKER=0 setsid nohup uv run uvicorn app.main:app --host \${HOST:-127.0.0.1} --port 8000 \
    >> data/preview.log 2>&1 < /dev/null &); cd ..; $HEALTH"
fi
echo
echo "== done"
