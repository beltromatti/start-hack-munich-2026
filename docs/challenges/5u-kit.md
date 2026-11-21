# 5U kit card: how we reach mailbox, portal and gateway

From 5U's kit card for team **START Milan** (Fehmi, Sat 21 Nov). Checked live on Sat 15:xx: `/v1/me` answers
`{"team": "start-milan", "mailbox": "start-milan@hackloop.mail"}`. First request at **16:00**.

**The key is not in this repo.** Get it from Jan in the team chat and put it in your local `.env` (below).
Everything sent with it counts as our team's. Lost key: 5U booth gives a new one.

## Access

| What | Value |
| --- | --- |
| Base URL | `https://api.start-hack.5u.ai` |
| Auth | header `X-API-Key: <key>` (or `Authorization: Bearer <key>`). One key for mailbox, portal, gateway |
| Our mailbox | `start-milan@hackloop.mail` |
| Swagger | `https://api.start-hack.5u.ai/docs`, spec saved in `5u-api/openapi.json` |
| Portal page (bot challenge) | `https://start-hack.5u.ai/portal/ui` |
| Leaderboard | `https://api.start-hack.5u.ai/board` (JSON: `/v1/board`, ours: `/v1/board/me`) |
| Start kit | unpacked in `5u-kit/start-kit/` (source: `/kit/start-kit.zip`) |

`.env` (repo root, gitignored):

```sh
FIVEU_BASE_URL=https://api.start-hack.5u.ai
FIVEU_API_KEY=<team key>
LLM_BASE_URL=https://api.start-hack.5u.ai/v1/gateway
LLM_API_KEY=<team key>          # same key. The gateway forwards to OpenAI and counts our cost
```

## Endpoints (from `5u-api/openapi.json`)

**Mailbox.** No push, so poll every 1 to 2 s. Response time is scored.
- `GET /v1/mailbox/messages?since_id=<n>&limit=200`: mail with id > n, oldest first. Keep `next_since_id`.
  Every kind arrives here: RFQs, carrier bids, rate desk answers, booking confirmations, tariff mails, tracking questions.
  `references` = thread ids from the first mail down to the parent.
- `GET /v1/mailbox/messages/{id}/attachments/{attachment_id}`: download an attachment.
- `POST /v1/mailbox/messages` `{to, subject, body, in_reply_to, attachments}`. **A quote counts only with
  `in_reply_to`** set inside a thread a 5U customer started, and only our first quote per thread.
  Allowed recipients: customers, carriers in `carrier-list.csv`, `ratedesk@hackloop.mail`,
  `tracking@hackloop.mail`. Anything else gets 422. Max 60 mails/min, 5 attachments of 10 MB.

**Portal.**
- `GET /v1/portal/ports`: lanes and which airlines serve them (not rate-limited).
- `GET /v1/portal/brackets?airline=`: weight breaks. 404 means the airline is not on the portal (email it).
- `GET /v1/portal/rates?origin&destination&airline&weight_kg[&volume_cbm]` → `rate_id, total, currency,
  chargeable_weight_kg, transit_days, valid_until, fx_eur_per_usd, dataset_version`. **Rate-limited per minute**:
  watch `X-RateLimit-Remaining`, 429 has `Retry-After`. 503 says where to get the rate instead.
- `POST /v1/portal/bookings {rate_id, team_reference}`: 201 booked, 200 retry, 404 unknown, 409 booked elsewhere,
  410 expired (fetch a fresh rate), 503 book by email. Confirmation mail "Booking <ref> confirmed" follows.
  There is no status call: tracking answers come from our own CRM.

**Gateway** (OpenAI-compatible, `base_url = .../v1/gateway`): `POST /chat/completions` (stream ok),
`/responses`, `/embeddings`, `GET /models`. Before the first call someone posts our own OpenAI key once:
`POST /v1/gateway/openai-key {"api_key": "sk-..."}`. State on Sat 15:xx: **not set** (`GET` returns `"set": false`).
A quote without any gateway call earns no cost points. Cost points land on the board hourly.

## Start kit (`5u-kit/start-kit/`)

- **11 rate sheets** in 6 formats: pdf (Cobalt, Helix, Orion), jpg in two pages (Danube Wings), xlsx (Elbflug, Kestrel,
  Vega, Wayzata), docx (Quetzal), txt (Yellowtail). Tariff month 2026-11.
- `carrier-list.csv` (`name, kind, email, serves`): 51 carriers, 22 of them truckers. `serves` lists destination airports.
- `pickup_zones.csv` (`zone, area, airport`): German postcode prefix → origin airport (FRA, MUC, DUS, HAM, STR, CGN).
  This is the door-to-port leg.
