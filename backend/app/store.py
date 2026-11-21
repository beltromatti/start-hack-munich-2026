"""SQLite store: an append-only event log (what every agent did) plus generic records (the CRM).

Events power the timeline in the UI, the token/cost numbers and the demo. Records are whatever the
challenge needs (quotes, shipments, suppliers, targets) as JSON, so no schema work before we know it.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  run_id TEXT,
  agent TEXT NOT NULL,
  kind TEXT NOT NULL,            -- start | llm | tool | decision | error | done | info
  summary TEXT NOT NULL,
  data TEXT,                     -- JSON
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id);
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,            -- e.g. rfq, quote, shipment, supplier, target
  status TEXT NOT NULL,
  data TEXT NOT NULL,            -- JSON
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS records_type ON records(type, updated_at);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if settings.db_path != ":memory:":
            Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def use_connection(c: sqlite3.Connection) -> None:
    """Tests: swap in an in-memory database."""
    global _conn
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    _conn = c


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def log(agent: str, kind: str, summary: str, data: Any = None, run_id: str | None = None,
        tokens_in: int = 0, tokens_out: int = 0) -> int:
    with _lock:
        cur = conn().execute(
            "INSERT INTO events(ts, run_id, agent, kind, summary, data, tokens_in, tokens_out) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), run_id, agent, kind, summary[:500],
             json.dumps(data, default=str) if data is not None else None, tokens_in, tokens_out),
        )
        conn().commit()
        return int(cur.lastrowid)


def events(since_id: int = 0, run_id: str | None = None, limit: int = 300) -> list[dict]:
    q = "SELECT * FROM events WHERE id > ?"
    args: list[Any] = [since_id]
    if run_id:
        q += " AND run_id = ?"
        args.append(run_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = conn().execute(q, args).fetchall()
    return [_event(r) for r in reversed(rows)]


def usage() -> dict:
    r = conn().execute(
        "SELECT COALESCE(SUM(tokens_in),0) AS tin, COALESCE(SUM(tokens_out),0) AS tout, "
        "COUNT(*) FILTER (WHERE kind='llm') AS calls FROM events"
    ).fetchone()
    return {"tokens_in": r["tin"], "tokens_out": r["tout"], "llm_calls": r["calls"]}


def upsert(type_: str, data: dict, status: str = "new", id_: str | None = None) -> str:
    now = time.time()
    rid = id_ or new_id(f"{type_}_")
    with _lock:
        conn().execute(
            "INSERT INTO records(id, type, status, data, created_at, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, data=excluded.data, updated_at=excluded.updated_at",
            (rid, type_, status, json.dumps(data, default=str), now, now),
        )
        conn().commit()
    return rid


def get(id_: str) -> dict | None:
    r = conn().execute("SELECT * FROM records WHERE id = ?", (id_,)).fetchone()
    return _record(r) if r else None


def records(type_: str | None = None, limit: int = 200) -> list[dict]:
    if type_:
        rows = conn().execute(
            "SELECT * FROM records WHERE type = ? ORDER BY updated_at DESC LIMIT ?", (type_, limit)).fetchall()
    else:
        rows = conn().execute("SELECT * FROM records ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [_record(r) for r in rows]


def _event(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"]) if d["data"] else None
    return d


def _record(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"])
    return d
