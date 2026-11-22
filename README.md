# START Hack Munich 2026

Team: Sam Sonntag, Jan Köberle, Mattia Beltrami. 21–22 Nov 2026, TUM Audimax.

**Our challenge: 5U AI, "Build the Forwarder"** (allocated Sat 21 Nov; we ranked Lio, 5U AI, revel8).
See `docs/challenges/5u.md`. A digital air forwarder: it reads the 5U mailbox, prices every request from the
portal, the rate sheets and carrier bids, replies in human words and books, all night, on its own.
The model reads and writes language; every number is computed in code.

**New here (or an AI assistant)? Read `vision.md` first, then `AGENTS.md`.**

## Key times

| When | What |
| --- | --- |
| Sat 13:00 | Hacking starts |
| Sat 16:00 | 5U AI: first RFQ, then one every 6 minutes all night |
| Sat 16:00 | Recruiting hour |
| Sun 12:45 | **Hard submission deadline** |
| Sun 13:15 | Demos: 3 min pitch, 2 min Q&A |
| Sun 20:00 | Lio: the fictional game launch |

## Run it

```sh
cp .env.example .env              # team key from the kit card, OpenAI key for dev
make install
make test                         # pricing rules + the whole flow against a fake 5U
make sim                          # realistic mails, real model (OpenAI direct, not scored), fake 5U
make api                          # http://127.0.0.1:8000  API only
make live                         # THE production forwarder (one machine only!)
make web                          # http://127.0.0.1:5173  the desk (dev); built (make build), it is on :8000
make account USERNAME=mattia NAME="Mattia Beltrami"   # the desk's sign-in (docs/deploy.md)
docker compose up -d --build      # the server: forwarder + API + UI on :8000 (docs/deploy.md)
deploy/tunnel.sh setup && deploy/tunnel.sh route && make tunnel   # the desk on its public address
```

## What is in here

| Path | What it does |
| --- | --- |
| `backend/app/agent.py` + `tools.py` | The forwarder agent: one session per thread (quote, book, track), tools over the engine. |
| `backend/app/forwarder.py` | The system under it: mail loop, routing, carrier replies, tariffs, bookings, the offer engine. |
| `backend/app/pricing.py` | Every number: chargeable weight, next weight break, minimum, surcharges, cheapest / fastest / balanced. |
| `backend/app/prompts/` | The agent's identity and tasks (soft guidance), plus the readers for carrier mails and tariffs. |
| `backend/app/llm.py` | The only model client: 5U gateway in production, OpenAI direct for dev. Tokens and USD per call. |
| `backend/app/fiveu.py` / `fake5u.py` | The 5U API (rate limit, outbound caps) and a local copy for tests. |
| `backend/app/kit.py` | Carriers, pickup zones, rate sheets (`docs/challenges/5u-kit/tariffs.json`), portal lanes. |
| `backend/app/store.py` | SQLite register: mails, records (rfq, booking, tariff), event log. |
| `backend/app/main.py` | The desk's API: `/api/deals`, `/api/deals/{id}`, `/api/sessions/{id}` (+ `/message`), `/api/ask`, `/api/login`, `/api/board`. |
| `backend/app/accounts.py` | Sign-in: accounts in the register, signed session cookie. |
| `backend/app/desk.py` | The desk's assistant: an agent over the register with read-only tools (our own key, never the gateway). |
| `backend/app/voice.py` | The voice desk: speech in (`llm.transcribe`) and out (ElevenLabs); meaning stays with `/api/ask`. |
| `frontend/` | The desk: what Giulia flagged, shipments, customers, network, efficiency, every session live; `/?voice`; `/leaderboard/challenge` for the team. |
| `docs/challenges/` | The 5U brief, slides, kit, API spec, counted facts. `docs/discussion-*.md`: team decisions. |
| `reference/` | Sempli AI layer (Sam) and SIEVER Mail vision (Mattia). Private, delete before going public. |
| `docs/transcripts/` | Raw Whisper transcripts of the talks (noisy, but complete). |

## Working together

- `main` must always run. Small commits, pull before you push. Bigger changes on a branch.
- Never commit keys. `.env` is ignored; share keys in the team chat, not in code.
- Business rules (prices, margins, who may be emailed) live in code, not in prompts.
- AI coding assistants: read `AGENTS.md` first.
