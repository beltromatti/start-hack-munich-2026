#!/usr/bin/env bash
# The desk on a public address through a Cloudflare Tunnel: the machine dials out to Cloudflare, so no port is
# opened and the forwarder can stay on the Mac. Reads CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN and DESK_HOSTNAME
# (default milan.noesisai.it) from .env; writes TUNNEL_TOKEN there. Every step can run again safely.
#
#   deploy/tunnel.sh setup   # the tunnel and where it points (localhost:8000); nothing public yet
#   deploy/tunnel.sh route   # DNS: the hostname to the tunnel (public once `run` is up)
#   deploy/tunnel.sh run     # the connector, in the foreground; refuses while the desk has no account
#   deploy/tunnel.sh down    # remove the DNS record: the address answers nothing again
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="${DESK_ENV:-$ROOT/.env}"
while IFS='=' read -r k v; do export "$k=$v"; done < <(grep -E '^(CLOUDFLARE_ACCOUNT_ID|CLOUDFLARE_API_TOKEN|DESK_HOSTNAME|TUNNEL_TOKEN|DESK_PORT)=' "$ENV" || true)
HOST="${DESK_HOSTNAME:-milan.noesisai.it}"
ZONE_NAME="${HOST#*.}"
NAME="milan-forwarding-desk"
PORT="${DESK_PORT:-8000}"
API="https://api.cloudflare.com/client/v4"

cf() {  # cf METHOD PATH [JSON]: one API call, the result printed, a failure stops the script
  local out args=(-sS -X "$1" "$API$2" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json")
  [ -z "${3:-}" ] || args+=(--data "$3")
  out=$(curl "${args[@]}")
  python3 -c 'import json,sys; d=json.loads(sys.argv[1]); sys.exit("Cloudflare: %s" % d.get("errors")) if not d.get("success") else print(json.dumps(d["result"]))' "$out"
}
field() { python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); r=r[0] if isinstance(r,list) and r else r; print((r or {}).get(sys.argv[1], "") if isinstance(r, dict) else "")' "$1"; }
keep() {  # keep KEY VALUE in .env (replaced if there)
  python3 - "$ENV" "$1" "$2" <<'PY'
import sys, pathlib
p, k, v = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = [l for l in p.read_text().splitlines() if not l.startswith(k + "=")]
p.write_text("\n".join(lines + [f"{k}={v}"]) + "\n")
PY
}
tunnel_id() { cf GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel?name=$NAME&is_deleted=false" | field id; }
zone_id() { cf GET "/zones?name=$ZONE_NAME" | field id; }

case "${1:-}" in
  setup)
    id=$(tunnel_id)
    if [ -z "$id" ]; then
      id=$(cf POST "/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel" "{\"name\":\"$NAME\",\"config_src\":\"cloudflare\"}" | field id)
      echo "tunnel $NAME created: $id"
    fi
    cf PUT "/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$id/configurations" \
      "{\"config\":{\"ingress\":[{\"hostname\":\"$HOST\",\"service\":\"http://127.0.0.1:$PORT\"},{\"service\":\"http_status:404\"}]}}" >/dev/null
    token=$(cf GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$id/token" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()))')
    keep TUNNEL_TOKEN "$token"
    keep DESK_HOSTNAME "$HOST"
    echo "tunnel $NAME ($id) points $HOST to 127.0.0.1:$PORT; its token is in .env. Not public until route + run."
    ;;
  route)
    id=$(tunnel_id); zone=$(zone_id)
    [ -n "$id" ] || { echo "no tunnel yet: deploy/tunnel.sh setup"; exit 1; }
    rec=$(cf GET "/zones/$zone/dns_records?name=$HOST" | field id)
    body="{\"type\":\"CNAME\",\"name\":\"$HOST\",\"content\":\"$id.cfargotunnel.com\",\"proxied\":true,\"comment\":\"Milan Forwarding desk (deploy/tunnel.sh)\"}"
    if [ -n "$rec" ]; then cf PUT "/zones/$zone/dns_records/$rec" "$body" >/dev/null; else cf POST "/zones/$zone/dns_records" "$body" >/dev/null; fi
    echo "https://$HOST -> tunnel $NAME"
    ;;
  run)
    [ -n "${TUNNEL_TOKEN:-}" ] || { echo "no TUNNEL_TOKEN in .env: deploy/tunnel.sh setup"; exit 1; }
    # A public desk without an account would be open to anyone: the register must hold one first.
    (cd "$ROOT/backend" && uv run python -c "import sys; from app import accounts, store; store.conn(); sys.exit(0 if accounts.any_() else 1)") \
      || { echo "the register holds no account: make account USERNAME=... NAME=... first"; exit 1; }
    exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
    ;;
  down)
    zone=$(zone_id); rec=$(cf GET "/zones/$zone/dns_records?name=$HOST" | field id)
    [ -z "$rec" ] || cf DELETE "/zones/$zone/dns_records/$rec" >/dev/null
    echo "$HOST removed from DNS"
    ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
