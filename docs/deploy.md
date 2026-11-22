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

## Sign-in

The desk is closed to anyone without an account once the register holds one. Accounts live in the register
(`backend/app/accounts.py`: a salted PBKDF2 hash, never the password; a signed session cookie for 14 days;
ten wrong passwords from one address in ten minutes, then a pause). With no account the desk is open, as on a laptop.

```sh
make account USERNAME=mattia NAME="Mattia Beltrami"     # prints a generated password once
cd backend && uv run python -m app.accounts list
```

Changes a person makes on the desk (a message to Giulia, a rate entered) are recorded under their account.
The challenge leaderboard is at `/leaderboard/challenge` for the team; the product does not link to it.

## Public address (Cloudflare Tunnel)

The machine dials out to Cloudflare, so no port is opened and production can stay on the Mac. Needs
`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` (Tunnel edit, DNS edit on the zone) in `.env`, and `cloudflared`
(`brew install cloudflared`). `DESK_HOSTNAME` defaults to `hackathon.noesisai.it`.

```sh
deploy/tunnel.sh setup    # the tunnel and where it points (127.0.0.1:8000); writes TUNNEL_TOKEN to .env
deploy/tunnel.sh route    # DNS: the hostname to the tunnel
make tunnel               # the connector; refuses while the register holds no account
deploy/tunnel.sh down     # take the address off DNS again
```

On a server with Docker: `docker compose --profile public up -d` runs the same connector next to the forwarder.

## Shared portal browser on the desk's Mac

Run `cd backend && uv run python -m app.browser` alongside the existing server. It listens only on
`127.0.0.1:8010`; it never polls or sends mail. The agent opens the installed desktop Chrome and the observer card
shares its page, keyboard, paste and scroll controls in the conversation. "Show on desktop" brings the same
tab forward for direct interaction. The agent handles checks and enters `{team_key}` from FIVEU_API_KEY; the UI is for observation, not required assistance.

Chrome uses `backend/data/portal-chrome/`, a private, gitignored profile whose cookies survive sidecar restarts.
It is launched directly, without headless mode, automation launcher flags, or device emulation. Playwright
attaches through a loopback CDP port with `no_defaults=True`. Keep the profile and CDP port private. Optional
`PORTAL_CHROME_PATH` and `PORTAL_BROWSER_PROFILE` override the executable and dedicated profile; never point it
at a personal browser profile. This needs a desktop session; a headless Docker server cannot provide it.
If the page changes or a check expires, the agent sees the actual error and can inspect a screenshot, reload and retry.
If the browser cannot run, the tool returns an error and the agent continues through available channels; it never
waits for a human answer. Alerts can be muted without affecting autonomy.

## Moving production between the Mac and a server over SSH (keeps every deal and session)

`deploy/push.sh` does it, from the repo root on the Mac (key `~/.ssh/amd_forwarder`):

```sh
deploy/push.sh user@host 22            # copy code, UI, .env; not live yet: a preview on a snapshot, NO forwarder
SWITCH=1 deploy/push.sh user@host 22   # stop the Mac, move the register, start the forwarder on the server
deploy/push.sh user@host 22            # after the switch: reload the new code on the server
BACK=1 deploy/push.sh user@host 22     # the reverse: stop the server, bring the register home, start the Mac
```

Switch right after a round's quote and booking (rounds come every 6 minutes). The server continues from the same
`since_id`: nothing is answered twice, and a mail that was mid-work is picked up again. The desk asks for a
sign-in once the register holds an account (`python -m app.accounts add`); `/api/health` stays open.

## Update to the latest main

```sh
git pull && docker compose up -d --build   # about a minute; the register stays
docker compose logs -f --tail 50            # live log
```
