# Context for AI coding assistants (Claude Code, Codex)

We are three people at a 24-hour hackathon (START Hack Munich, 21–22 Nov 2026). Hard deadline Sunday 12:45.
Ship a working, demoable agent system. Speed and a clean demo beat completeness.

**Read `vision.md` first:** how we think about this system and why (the model decides, the system guarantees;
one agent per deal; intelligence in the agent, guarantees in tools), the decisions we took with the rounds
that taught them, and what is still open. Keep it true: a decision that changes is changed there.

## The challenge

**Allocated: 5U AI, "Build the Forwarder"** (confirmed in the Hack League app, Sat 21 Nov).
Read `docs/challenges/5u.md` before building anything. The other challenge files are background only.
How to reach 5U (mailbox, rate portal, LLM gateway, endpoints, `.env` names): `docs/challenges/5u-kit.md`.
API spec: `docs/challenges/5u-api/openapi.json`. Rate sheets, carrier list, pickup zones: `docs/challenges/5u-kit/start-kit/`.
Counted facts for decisions (lanes, rate limit, email-only airlines, weight breaks, trucker zones): `docs/challenges/5u-facts.md`.
What 5U will likely change each hour, the earliest signal and our response: `docs/likely-changes.md`.
The 10 rate sheets as one checked table (158 lanes, EUR per kg, minimum, surcharges): `docs/challenges/5u-kit/tariffs.json`.
Read it instead of the raw pdf/xlsx/jpg files. Pricing: also price the next weight break up and take the cheaper
(299 kg cost more than 300 kg on the portal, see `5u-facts.md`).
The team key never goes into the repo. It lives only in each person's `.env`.
Feed a mail into the local 5U with `FakeFiveU.customer(m["frm"], m["subject"], m["body"])` and compare the quote with
the key. Forwarder vocabulary for the parse prompt: `backend/app/prompts/glossary.md`.

## Architecture (keep it this simple)

One forwarder agent (SIEVER Mail harness, `reference/siever-mail/`): the model decides, the system guarantees.

```
mail in -> register (SQLite) -> router (code, by sender/thread)
  customer / tracking -> the forwarder agent, ONE SESSION PER THREAD, resumed by every new mail in it
                         tools: get_offers, send_mail, book, crm, deal, mail_carrier, carrier_status, note, no_reply
  carrier / rate desk -> read into offers on the deal (small model); wakes nobody, except a booking confirmation
  tariff              -> pricing module (txt, xlsx, docx, pdf, scanned images)
```

- `backend/app/agent.py` the harness: sessions in the register (restart-safe, cache-warm), the required outcome
  (a mail is answered, or a reasoned no_reply) as the one system constraint, one stop for spinning (10 turns
  without progress). No caps on steps, tokens or output: the model decides how much work a deal needs.
- `browser.py` the shared desktop Chrome: the agent reads text or screenshots, batches inputs and handles page
  checks itself. `{team_key}` resolves from the environment; `save_rate` returns computed options. The live UI
  and alerts observe progress. The organiser clarified at 04:03: no human assistance, including the portal.
- `tools.py` the tools: thin over the engine. They guarantee what must be guaranteed (totals computed by code,
  mails only to people in the thread and carriers on the list, the first quote recorded with its option).
- `forwarder.py` the system under the agent: polling, routing, carrier replies, tariffs, bookings, board watcher,
  and the engine (ask carriers + portal + sheets, wait, options, booking by rate_id or by mail).
- `pricing.py` every number a customer sees (Decimal, chargeable weight, next break, minimum, surcharges, pick).
- `prompts/forwarder.md` identity (business, how we are judged, how we write); `prompts/tasks/*.md` per task.
  Soft guidance and criteria, never procedures. `bid.md`, `tariff.md`: the small model reading data for tools.
- `llm.py` the only model client (5U gateway in production; `LLM_TARGET=openai` for dev, never scored). Waits
  through transient errors, OpenAI direct if the gateway is down. Tokens and USD per call.
- `fiveu.py` the 5U API (rate limit, outbound caps); `fake5u.py` a local 5U whose carriers answer like the real
  ones: use it for all experiments. `kit.py` carriers, zones, sheets, portal lanes. `store.py` the register.
- `main.py` API for the sessions UI: `/api/deals`, `/api/deals/{id}` (mails, events, session transcript, cost),
  `/api/sessions/{id}`, `POST /api/sessions/{id}/message` (a person steps in), `POST /api/deals/{id}/reply`,
  `/api/bookings`, `/api/board`.
- **Only one machine runs `make live`** (it polls and answers the real mailbox). Everyone else: `make sim`,
  `make test`, the fake 5U. The portal rate limit (10/min) is shared by the whole team key.
- `frontend/` the sessions UI (Vite + React + TS, plain CSS tokens in `src/styles.css`, light and dark): deals (the
  CRM), each deal's live agent session (mails, steps, priced options, booking, airline status), a composer to tell
  the agent something or reply yourself, the leaderboard and our verdicts. Built into `frontend/dist`, it is served
  by the backend on :8000 (`npm run build`); `make web` for development.
- Server: `Dockerfile` + `docker-compose.yml`, one container, register on a volume (`docs/deploy.md`).
- `personal/` is gitignored, for each person's private notes.

## Rules

1. Prices, totals, dates and IDs are computed in code (tools); the model decides and writes. A price in a mail
   that no tool computed is a bug. Guarantees live in tools and the register, not in checks on the model's text.
2. Missing information: ask (customer, supplier) instead of guessing.
3. Never spam real or simulated counterparts: rate-limit outbound mail per recipient.
4. No secrets in code or commits. `.env` only.
5. Small, working steps. `make test` stays green. Add a test for anything that touches money or sending.
6. Prefer deleting over adding layers. No new framework without asking the team.

## Before you change anything

The reasoning is in `vision.md`. In short: a new capability is a tool or a field a tool returns, not a
step in front of the agent; no hard checks on what the model writes (teach with the prompt, measure with
diagnostics); one implementation per thing; fix the kind of change, not the one mail; prompts give goals and
reasons. Work on a short branch from `main`, `make test` and `make sim`, let Mattia merge, never `make live`.

## Commands

```sh
make install   # backend (uv) + frontend (npm)
make api       # backend API on :8000, no forwarder loop
make live      # production forwarder on the real mailbox (ONE machine only)
make sim       # realistic mails, real model (OpenAI direct), fake 5U
make web       # dashboard on :5173 (proxies /api)
make test      # backend tests
```
