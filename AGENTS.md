# Context for AI coding assistants (Claude Code, Codex)

We are three people at a 24-hour hackathon (START Hack Munich, 21–22 Nov 2026). Hard deadline Sunday 12:45.
Ship a working, demoable agent system. Speed and a clean demo beat completeness.

## The challenge

**Allocated: 5U AI, "Build the Forwarder"** (confirmed in the Hack League app, Sat 21 Nov).
Read `docs/challenges/5u.md` before building anything. The other challenge files are background only.

## Architecture (keep it this simple)

- `backend/` Python 3.12, FastAPI, SQLite, `uv`. Entry `app/main.py`.
- Every model call goes through `app/llm.py` (`chat`, `ask_json`). Never instantiate a model client elsewhere:
  token cost may be scored and a challenge may force its own gateway (`LLM_BASE_URL`).
- Structured, cost-sensitive calls (extract, classify, write) use `app/ai/service.generate_structured` with a
  stage profile from `app/ai/profiles.stage(...)`. Every call stores tokens and `cost_usd`; `LLM_BUDGET_USD` stops at 90 %.
- Agents use `app/agent.py` (`@tool` + `run`). Tools do the work and enforce rules; the model decides.
- Everything an agent does is logged with `store.log(...)`; the dashboard and the pitch depend on it.
- Domain data goes into `store.upsert(type, data, status)` until a real schema is clearly needed.
- New inputs (mailbox API, portal, supplier mail) are adapters in `app/channels/` behind a small interface,
  with a fake for local testing.
- `frontend/` Vite + React + TypeScript. Plain CSS in `src/styles.css`, light and dark.

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
make api       # backend on :8000
make web       # dashboard on :5173 (proxies /api)
make test      # backend tests
```
