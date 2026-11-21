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
