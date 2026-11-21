# START Hack Munich 2026

Team: Sam Sonntag, Jan Köberle, Mattia Beltrami. 21–22 Nov 2026, TUM Audimax.

Challenge preference: **1. Lio** (procurement / supply chain), **2. 5U AI** (freight forwarding), **3. revel8**
(social engineering). Allocation is announced at 12:55. This repo is the shared foundation that works for any of
the three: agents that read a mailbox, call tools, write to a small CRM and show every step live.

## Key times

| When | What |
| --- | --- |
| Sat 13:00 | Hacking starts |
| Sat ~15:00 | 5U AI: first emails, then one every 6 minutes all night |
| Sat 16:00 | Recruiting hour |
| Sun 12:45 | **Hard submission deadline** |
| Sun 13:15 | Demos: 3 min pitch, 2 min Q&A |
| Sun 20:00 | Lio: the fictional game launch |

## Run it

```sh
cp .env.example .env              # add LLM_API_KEY (OpenAI credits) or the challenge gateway
make install
make api                          # http://127.0.0.1:8000  (backend, FastAPI)
make web                          # http://127.0.0.1:5173  (dashboard, Vite + React)
make test
```

Try the loop without any API: set `WORKER=1`, drop a JSON mail into `backend/data/inbox/`
(`{"from": "a@b.c", "subject": "...", "body": "..."}`) and watch it appear in the dashboard.

## What is in here

| Path | What it does |
| --- | --- |
| `backend/app/llm.py` | All model calls. OpenAI-compatible, so OpenAI, a challenge gateway or OpenRouter. Logs tokens per call. |
| `backend/app/agent.py` | Small tool-calling loop. `@tool` turns a typed function into a tool. Every step is logged. |
| `backend/app/store.py` | SQLite: `events` (agent timeline, tokens) and `records` (generic CRM: quotes, shipments, suppliers…). |
| `backend/app/channels/mail.py` | Mailbox interface + `FakeMail` (local files). One adapter per challenge goes here. |
| `backend/app/worker.py` | Background loop: poll → route → handle. One bad item never stops the loop. |
| `backend/app/main.py` | API for the dashboard: `/api/events`, `/api/usage`, `/api/records`, `/api/tick`. |
| `frontend/` | Agent console: live timeline, runs, token count. The base for the demo UI. |
| `docs/challenges/` | The problem sets as presented, one file per challenge. |
| `docs/transcripts/` | Raw Whisper transcripts of the talks (noisy, but complete). |

## Working together

- `main` must always run. Small commits, pull before you push. Bigger changes on a branch.
- Never commit keys. `.env` is ignored; share keys in the team chat, not in code.
- Business rules (prices, margins, who may be emailed) live in code, not in prompts.
- AI coding assistants: read `AGENTS.md` first.
