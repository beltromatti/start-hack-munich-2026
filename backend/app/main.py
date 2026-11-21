"""HTTP API for the sessions UI, and the forwarder loop when WORKER=1.

Run: uv run uvicorn app.main:app --port 8000   (make api / make live)
"""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import store
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
            "models": {"parse": settings.model_parse, "bid": settings.model_bid, "write": settings.model_write}}


@app.get("/api/events")
def events(since: int = 0, run_id: str | None = None) -> list[dict]:
    return store.events(since, run_id)


@app.get("/api/usage")
def usage() -> dict:
    return store.usage()


@app.get("/api/rfqs")
def rfqs() -> list[dict]:
    return [{"id": r["id"], "status": r["status"], "updated_at": r["updated_at"], "customer": r["data"].get("customer"),
             "subject": r["data"].get("subject"), "request": r["data"].get("request"), "amount": r["data"].get("amount"),
             "response_seconds": r["data"].get("response_seconds"), "cost": store.usage(r["id"])["cost_usd"]}
            for r in store.records("rfq")]


@app.get("/api/rfqs/{rid}")
def rfq(rid: str) -> dict:
    r = store.get(rid)
    if not r:
        raise HTTPException(404)
    return {**r, "mails": store.thread(r["data"]["root"]), "events": store.events(run_id=rid),
            "usage": store.usage(rid)}


@app.get("/api/bookings")
def bookings() -> list[dict]:
    return store.records("booking")


@app.get("/api/mails")
def mails(limit: int = 200) -> list[dict]:
    return store.mails(limit)


@app.get("/api/board")
def board() -> dict:
    return json.loads(store.kv_get("board_me") or "{}")


# ---- a person steps in (the human's word wins: the loop never undoes it) -----------------------------------

def _live():
    if forwarder is None:
        raise HTTPException(409, "the forwarder is not running here (WORKER=1 / make live)")
    return forwarder


@app.post("/api/rfqs/{rid}/hold")
def hold(rid: str) -> dict:
    """Stop the automatic quote for this request (while it is still being priced)."""
    r = store.update(rid, lambda r: ("held", r["data"]) if r["status"] in ("pricing", "collecting") else None)
    if not r:
        raise HTTPException(404)
    store.log("human", "decision", f"held {rid} (was it already quoted? status {r['status']})", run_id=rid)
    return {"status": r["status"]}


@app.post("/api/rfqs/{rid}/release")
def release(rid: str) -> dict:
    """Hand a held request back to the forwarder: it quotes now with the offers it has."""
    r = store.update(rid, lambda r: ("collecting", {**r["data"], "deadline": 0}) if r["status"] == "held" else None)
    if not r:
        raise HTTPException(404)
    store.log("human", "decision", f"released {rid}", run_id=rid)
    return {"status": r["status"]}


@app.post("/api/rfqs/{rid}/reply")
def human_reply(rid: str, payload: dict) -> dict:
    """Send a reply written by a person in the customer's thread. If nothing was quoted yet, this is the quote."""
    f = _live()
    r = store.get(rid)
    body = (payload.get("body") or "").strip()
    if not r or not body:
        raise HTTPException(400, "unknown request or empty body")
    m = store.mail(r["data"]["last_customer_mail"])
    sent = f.reply_customer(rid, m, body)
    store.update(rid, lambda x: ("quoted" if x["status"] in ("pricing", "collecting", "held", "waiting_customer")
                                 else x["status"], {**x["data"], "human_reply": sent["id"]}))
    store.log("human", "mail_out", f"human reply in {rid}", {"body": body}, run_id=rid)
    return {"sent": sent["id"]}
