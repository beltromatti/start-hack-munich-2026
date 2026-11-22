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

## Shared portal browser on the desk's Mac

Run `cd backend && uv run python -m app.browser` alongside the existing server. It listens only on
`127.0.0.1:8010`; it never polls or sends mail. The operator's card opens the installed desktop Chrome and
shares its page, keyboard, paste and scroll controls in the conversation. "Show on desktop" brings the same
tab forward for direct interaction. The check and team key remain the person's responsibility.

Chrome uses `backend/data/portal-chrome/`, a private, gitignored profile whose cookies survive sidecar restarts.
It is launched directly, without headless mode, automation launcher flags, or device emulation. Playwright
attaches through a loopback CDP port with `no_defaults=True`. Keep the profile and CDP port private. Optional
`PORTAL_CHROME_PATH` and `PORTAL_BROWSER_PROFILE` override the executable and dedicated profile; never point it
at a personal browser profile. This needs a desktop session; a headless Docker server cannot provide it.
If Chrome cannot start or Cloudflare still refuses the check, the card retains the external-browser/paste path.

## Moving production between the Mac and a server over SSH (keeps every deal and session)

`deploy/push.sh` does it, from the repo root on the Mac (key `~/.ssh/amd_forwarder`):

```sh
deploy/push.sh user@host 22            # copy code, UI, .env; not live yet: a preview on a snapshot, NO forwarder
SWITCH=1 deploy/push.sh user@host 22   # stop the Mac, move the register, start the forwarder on the server
deploy/push.sh user@host 22            # after the switch: reload the new code on the server
BACK=1 deploy/push.sh user@host 22     # the reverse: stop the server, bring the register home, start the Mac
```

Switch right after a round's quote and booking (rounds come every 6 minutes). The server continues from the same
`since_id`: nothing is answered twice, and a mail that was mid-work is picked up again. With `UI_PASSWORD` in
`.env` the UI and API ask for the team password (any user name); `/api/health` stays open.

## Update to the latest main

```sh
git pull && docker compose up -d --build   # about a minute; the register stays
docker compose logs -f --tail 50            # live log
```
