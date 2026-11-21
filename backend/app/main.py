"""HTTP API for the sessions UI, and the forwarder loop when WORKER=1.

Run: uv run uvicorn app.main:app --port 8000   (make api / make live)
"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import agent, store
from .config import settings

forwarder = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global forwarder
    store.conn()
    if settings.worker:
        from .fiveu import FiveU
        from .forwarder import Forwarder
        forwarder = Forwarder(FiveU())
        forwarder.start()
    yield
    if forwarder:
        forwarder.stop.set()


app = FastAPI(title="START Milan Forwarding", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "worker": settings.worker, "llm": settings.llm_base_url or "openai",
            "models": {"agent": settings.model_agent, "effort": settings.effort_agent, "bid": settings.model_bid,
                       "parse": settings.model_agent}}


@app.get("/api/events")
def events(since: int = 0, run_id: str | None = None) -> list[dict]:
    return store.events(since, run_id)


@app.get("/api/usage")
def usage() -> dict:
    return store.usage()


@app.get("/api/deals")
def deals() -> list[dict]:
    """Every deal, newest first: the CRM list (status, customer, route, quote, booking, flag, cost)."""
    out = []
    for r in store.records("deal"):
        d = r["data"]
        req = d.get("request") or {}
        out.append({"id": r["id"], "status": r["status"], "updated_at": r["updated_at"], "customer": d.get("customer"),
                    "subject": d.get("subject"), "route": f"{req.get('origin')}-{req.get('destination')}" if req else None,
                    "weight_kg": req.get("weight_kg"), "preference": d.get("preference"),
                    "quote": (d.get("quote") or {}).get("amount"),
                    "response_seconds": (d.get("quote") or {}).get("response_seconds"),
                    "booking": (d.get("booking") or {}).get("booking_reference"), "flag": d.get("flag"),
                    "cost_usd": store.usage(r["id"])["cost_usd"]})
    return out


@app.get("/api/rfqs")
def rfqs() -> list[dict]:
    return deals()


@app.get("/api/deals/{deal_id}")
def deal(deal_id: str) -> dict:
    r = store.get(deal_id)
    if not r:
        raise HTTPException(404)
    root = r["data"]["root"]
    s = store.get(f"session-{root}")
    return {**r, "mails": store.thread(root), "events": store.events(run_id=deal_id), "usage": store.usage(deal_id),
            "session": {"status": s["status"], "items": s["data"].get("items", [])} if s else None}


@app.get("/api/sessions")
def sessions() -> list[dict]:
    return [{"id": s["id"], "status": s["status"], "task": s["data"]["task"], "root": s["data"]["root"],
             "executions": s["data"]["executions"], "updated_at": s["updated_at"]} for s in store.records("session")]


@app.get("/api/sessions/{session_id}")
def session(session_id: str) -> dict:
    s = store.get(session_id)
    if not s:
        raise HTTPException(404)
    return s


@app.post("/api/sessions/{session_id}/message")
def message(session_id: str, payload: dict) -> dict:
    """A person writes into a session: the forwarder resumes it and follows them (their word wins)."""
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty message")
    s = agent.operator_message(session_id, text, payload.get("who") or "operator")
    if not s:
        raise HTTPException(404)
    store.log("human", "decision", f"message to {session_id}: {text[:200]}", run_id=f"deal-{s['data']['root']}")
    return {"status": s["status"]}


@app.post("/api/deals/{deal_id}/reply")
def human_reply(deal_id: str, payload: dict) -> dict:
    """A person answers the customer directly, in the thread."""
    if forwarder is None:
        raise HTTPException(409, "the forwarder is not running here (make live)")
    r = store.get(deal_id)
    body = (payload.get("body") or "").strip()
    if not r or not body:
        raise HTTPException(400, "unknown deal or empty body")
    from . import tools
    ctx = tools.Ctx(forwarder, f"session-{r['data']['root']}", deal_id, r["data"]["root"], "customer", None)
    out = tools.send_mail(ctx, payload.get("kind") or "reply", body, payload.get("option_id"), None)
    store.log("human", "mail_out", f"human reply in {deal_id}", {"body": body}, run_id=deal_id)
    return out


@app.get("/api/bookings")
def bookings() -> list[dict]:
    return store.records("booking")


@app.get("/api/mails")
def mails(limit: int = 200) -> list[dict]:
    return store.mails(limit)


@app.get("/api/board")
def board() -> dict:
    """Ours (verdict and points per request) and the public board (every team), as last fetched."""
    return {"me": json.loads(store.kv_get("board_me") or "{}"), "public": json.loads(store.kv_get("board") or "{}")}


@app.get("/api/board/history")
def board_history(limit: int = 200) -> list[dict]:
    return [r["data"] for r in store.records("board", limit=limit)]


# The sessions UI, built (frontend/dist): served by the same process on a server (Docker), so one port is enough.
_dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
