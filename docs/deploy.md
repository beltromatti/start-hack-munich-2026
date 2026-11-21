# Deploy: the forwarder on a server (AMD cloud or any Linux box)

One container runs everything: the forwarder loop (polls the 5U mailbox, answers, books), the API and the
sessions UI on port 8000. The register (SQLite) lives in `backend/data/` on the host, so rebuilds keep every deal.

**Exactly one production instance per team key.** Two pollers on one mailbox answer twice. Stop the old one first.

## First time

```sh
git clone git@github.com:SLS-NW/start-hack-munich-2026.git && cd start-hack-munich-2026
cp .env.example .env            # team key + OpenAI key (never commit it)
docker compose up -d --build
curl localhost:8000/api/health  # {"ok": true, "worker": true, ...}
```

UI: `http://<server>:8000`. Behind a firewall: `ssh -L 8000:localhost:8000 <server>` and open `localhost:8000`.

## Moving production from the Mac to the server (keeps every deal and session)

1. On the Mac: stop `make live` (Ctrl+C in its terminal, or `pkill -f backend/live.sh; pkill -f "uvicorn app.main:app --port 8000"`).
2. Copy the register: `scp backend/data/forwarder.db* <server>:start-hack-munich-2026/backend/data/`
3. On the server: `docker compose up -d --build`. It continues from the same `since_id`: nothing answered twice.

## Update to the latest main

```sh
git pull && docker compose up -d --build   # about a minute; the register stays
docker compose logs -f --tail 50            # live log
```
