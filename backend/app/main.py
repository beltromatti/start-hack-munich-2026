"""HTTP API for the dashboard. Run: uv run uvicorn app.main:app --reload --port 8000"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import store, worker
from .channels.mail import adapter
from .config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.conn()
    task = asyncio.create_task(worker.loop()) if settings.worker else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="START Hack Munich 2026", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model": settings.llm_model, "worker": settings.worker, "mail": settings.mail_adapter}


@app.get("/api/events")
def events(since: int = 0, run_id: str | None = None) -> list[dict]:
    return store.events(since, run_id)


@app.get("/api/usage")
def usage() -> dict:
    return store.usage()


@app.get("/api/records")
def records(type: str | None = None) -> list[dict]:
    return store.records(type)


@app.post("/api/tick")
def tick() -> dict:
    """Run one worker cycle by hand (useful for demos and debugging)."""
    return {"handled": worker.tick(adapter(settings.mail_adapter))}
