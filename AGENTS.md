# Context for AI coding assistants (Claude Code, Codex)

We are three people at a 24-hour hackathon (START Hack Munich, 21–22 Nov 2026). Hard deadline Sunday 12:45.
Ship a working, demoable agent system. Speed and a clean demo beat completeness.

## The challenge

**Allocated: 5U AI, "Build the Forwarder"** (confirmed in the Hack League app, Sat 21 Nov).
Read `docs/challenges/5u.md` before building anything. The other challenge files are background only.
How to reach 5U (mailbox, rate portal, LLM gateway, endpoints, `.env` names): `docs/challenges/5u-kit.md`.
API spec: `docs/challenges/5u-api/openapi.json`. Rate sheets, carrier list, pickup zones: `docs/challenges/5u-kit/start-kit/`.
Counted facts for decisions (lanes, rate limit, email-only airlines, weight breaks, trucker zones): `docs/challenges/5u-facts.md`.
The 10 rate sheets as one checked table (158 lanes, EUR per kg, minimum, surcharges): `docs/challenges/5u-kit/tariffs.json`.
Read it instead of the raw pdf/xlsx/jpg files. Pricing: also price the next weight break up and take the cheaper
(299 kg cost more than 300 kg on the portal, see `5u-facts.md`).
The team key never goes into the repo. It lives only in each person's `.env`.
Test data: 31 synthetic 5U mails (every mail kind, DE/IT/ES/FR/EN, the hard cases) in `backend/synthetic/mails.py`,
their answer key with computed prices (sheets plus 34 live portal rates) in `backend/synthetic/expected.json`.
Feed a mail into the local 5U with `FakeFiveU.customer(m["frm"], m["subject"], m["body"])` and compare the quote with
the key. Forwarder vocabulary for the parse prompt: `backend/app/prompts/glossary.md`.

## Architecture (keep it this simple)

A workflow, not a free agent: the model reads and writes language, code does everything else.

```
mail in -> register (SQLite) -> router (code, by sender/thread) -> one handler per kind
customer  read (LLM, strict JSON form) -> ask carriers by mail + portal API + sheets (code) -> wait for bids
          -> price and pick (code: cheapest / fastest / 50-50 balanced) -> write (LLM) -> reply in the thread
          follow-ups: accept -> book (portal by rate_id, else by mail to the airline); questions -> reply
bid       read (LLM) -> offers on the rfq          tracking  answer from the CRM (code facts, LLM words)
tariff    attachment -> text -> lanes (LLM) -> pricing module (replaces that airline's sheet)
```

- `backend/app/forwarder.py` the loop and the handlers. Work is derived from the register, so a restart loses
  nothing and never quotes twice. One lane per thread, threads in parallel.
- `pricing.py` every number a customer sees (Decimal, chargeable weight, next break, minimum, surcharges, pick).
- `language.py` the forms the model fills (the flexibility layer: `flags`, `missing`, `notes` catch what does not
  fit) and `write()`, which checks in code that a mail contains exactly the computed amount and no other.
- `prompts/*.md` one prompt per step: goals and criteria, not procedures.
- `llm.py` the only model client (5U gateway in production; `LLM_TARGET=openai` for dev and tests, never scored).
  Models per step in `config.py`. Every call logs tokens and USD.
- `fiveu.py` the 5U API (rate limit and outbound caps enforced here). `fake5u.py` a local 5U with carriers that
  answer like the real ones: use it for all experiments.
- `kit.py` carriers, zones, sheets (`docs/challenges/5u-kit/tariffs.json` + ingested tariffs), portal lanes.
- `store.py` register: `mails`, `records` (rfq, booking, tariff), `events` (every step, the sessions UI reads it).
- `main.py` API for the UI: `/api/rfqs`, `/api/rfqs/{id}` (mails, events, cost), `/api/bookings`, `/api/board`.
- **Only one machine runs `make live`** (it polls and answers the real mailbox). Everyone else: `make sim`,
  `make test`, the fake 5U. The portal rate limit (10/min) is shared by the whole team key.
- `frontend/` Vite + React + TypeScript. Plain CSS in `src/styles.css`, light and dark.
- How Mattia builds agent systems (state-driven work, the register as truth, tools enforce rules):
  `reference/siever-mail/README.md`. `personal/` is gitignored, for each person's private notes.

## Rules

1. Deterministic where possible: prices, totals, dates and IDs are computed in code. The model extracts and
   writes text. If a number in model output was not computed by code, treat it as a bug.
2. Missing information: ask (customer, supplier) instead of guessing.
3. Never spam real or simulated counterparts: rate-limit outbound mail per recipient.
4. No secrets in code or commits. `.env` only.
5. Small, working steps. `make test` stays green. Add a test for anything that touches money or sending.
6. Prefer deleting over adding layers. No new framework without asking the team.

## Commands

```sh
make install   # backend (uv) + frontend (npm)
make api       # backend API on :8000, no forwarder loop
make live      # production forwarder on the real mailbox (ONE machine only)
make sim       # realistic mails, real model (OpenAI direct), fake 5U
make web       # dashboard on :5173 (proxies /api)
make test      # backend tests
```
