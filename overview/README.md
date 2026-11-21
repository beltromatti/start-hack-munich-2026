# Forwarder Overview (read-only)

Live team overview, design M3 (Fey insider × Revolut numbers). Cloudflare Worker on Sam's personal account:
https://forwarder-overview.samsonntag11.workers.dev (sign in with an allowlisted email + team password, ask Sam).

- Reads 5U only: `/v1/board`, `/v1/board/me`, `/v1/mailbox/messages`, `/v1/mailbox/messages/{id}` through
  `/api/5u/*`. GET only; everything else returns 404/405. It cannot send mail, book or touch the gateway.
- Secrets (never in git): `FIVEU_API_KEY`, `PASSWORD` (team password), `SESSION_SECRET`, `ALLOWED_EMAILS` (comma list).
  Session = HMAC-signed cookie, 3 days.
- Tabs: Requests (needs attention, points per request, latest requests), Inbox (every mail, kind by sender),
  Standings (all 14 teams, us highlighted). Polls every 10 s.
- Local: put the four secrets in `overview/.dev.vars` (gitignored), then `npx wrangler dev`.
- Deploy: `cd overview && npx wrangler deploy`. In the Munich venue network wrangler needs
  `NODE_OPTIONS="--no-network-family-autoselection --dns-result-order=ipv6first"`.
- Next: Mattia's `/api/rfqs` and `/api/rfqs/{id}` (sessions, costs) once his API is reachable via a tunnel.
