"""SQLite register: every mail in and out, the CRM records (rfq, booking, tariff) and an append-only event log.

The register is the truth; the dashboard and every answer we give are projections of it. Records have
deterministic ids (`rfq-<thread root>`), so doing the same work twice never creates a second record.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  run_id TEXT,                   -- the thread / record the event belongs to
  agent TEXT NOT NULL,           -- router | rfq | bids | booking | tracking | tariff | llm | watcher
  kind TEXT NOT NULL,            -- llm | mail_in | mail_out | decision | error | info
  summary TEXT NOT NULL,
  data TEXT,
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  cost_usd REAL
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id);
CREATE TABLE IF NOT EXISTS mails (
  id INTEGER PRIMARY KEY,        -- 5U mail id
  direction TEXT NOT NULL,       -- in | out
  sender TEXT NOT NULL,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  in_reply_to INTEGER,
  root INTEGER NOT NULL,         -- first mail of the thread
  received_at TEXT,
  attachments TEXT,
  kind TEXT,                     -- customer | bid | tracking | ratedesk | tariff | booking | other
  handled INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS mails_root ON mails(root);
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,            -- rfq | booking | tariff
  status TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS records_type ON records(type, updated_at);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if settings.db_path != ":memory:":
            Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
    return _conn


def use_connection(c: sqlite3.Connection) -> None:
    """Tests: an in-memory database."""
    global _conn
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    _conn = c


def _q(sql: str, args: Any = ()) -> list[sqlite3.Row]:
    """Every read goes through the lock: one connection is shared by the loop and the worker threads."""
    with _lock:
        return conn().execute(sql, args).fetchall()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


# ---- event log ---------------------------------------------------------------------------------------------

def log(agent: str, kind: str, summary: str, data: Any = None, run_id: str | None = None,
        tokens_in: int = 0, tokens_out: int = 0, cost_usd: float | None = None) -> int:
    with _lock:
        cur = conn().execute(
            "INSERT INTO events(ts, run_id, agent, kind, summary, data, tokens_in, tokens_out, cost_usd) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), run_id, agent, kind, summary[:500],
             json.dumps(data, default=str) if data is not None else None, tokens_in, tokens_out, cost_usd))
        conn().commit()
        return int(cur.lastrowid)


def events(since_id: int = 0, run_id: str | None = None, limit: int = 300) -> list[dict]:
    q, args = "SELECT * FROM events WHERE id > ?", [since_id]
    if run_id:
        q += " AND run_id = ?"
        args.append(run_id)
    rows = _q(q + " ORDER BY id DESC LIMIT ?", [*args, limit])
    return [_row(r, "data") for r in reversed(rows)]


def usage(run_id: str | None = None) -> dict:
    q = ("SELECT COALESCE(SUM(tokens_in),0) tin, COALESCE(SUM(tokens_out),0) tout, "
         "COUNT(*) FILTER (WHERE kind='llm') calls, COALESCE(SUM(cost_usd),0) cost FROM events")
    r = _q(q + (" WHERE run_id = ?" if run_id else ""), (run_id,) if run_id else ())[0]
    return {"tokens_in": r["tin"], "tokens_out": r["tout"], "llm_calls": r["calls"], "cost_usd": round(r["cost"], 6)}


# ---- mails -------------------------------------------------------------------------------------------------

def save_mail(m: dict, direction: str, kind: str | None = None, handled: bool = False) -> bool:
    """Insert once; returns False if we already had it."""
    refs = m.get("references") or []
    root = refs[0] if refs else m["id"]
    with _lock:
        cur = conn().execute(
            "INSERT OR IGNORE INTO mails(id, direction, sender, recipient, subject, body, in_reply_to, root, "
            "received_at, attachments, kind, handled) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (m["id"], direction, m.get("from", ""), m.get("to", ""), m.get("subject") or "", m.get("body") or "",
             m.get("in_reply_to"), root, m.get("received_at"), json.dumps(m.get("attachments") or []), kind,
             1 if handled else 0))
        conn().commit()
        return cur.rowcount == 1


def mail(mail_id: int) -> dict | None:
    r = next(iter(_q("SELECT * FROM mails WHERE id = ?", (mail_id,))), None)
    return _row(r, "attachments") if r else None


def thread(root: int) -> list[dict]:
    return [_row(r, "attachments") for r in _q("SELECT * FROM mails WHERE root = ? ORDER BY id", (root,))]


def carrier_mails(deal_id: str) -> list[dict]:
    """The carriers' replies to the requests we sent for a deal (each request starts its own thread)."""
    sent = [int(r[0].split(":", 1)[1]) for r in _q("SELECT k FROM kv WHERE k LIKE 'bidreq:%' AND v = ?", (deal_id,))]
    if not sent:
        return []
    marks = ",".join("?" * len(sent))
    mails = [_row(r, "attachments") for r in _q(
        f"SELECT * FROM mails WHERE direction='in' AND (root IN ({marks}) OR in_reply_to IN ({marks})) ORDER BY id",
        tuple(sent) + tuple(sent))]
    return [{**m, "read": kv_get(f"read:{m['id']}")} for m in mails]


def mail(mail_id: int) -> dict | None:
    r = _q("SELECT * FROM mails WHERE id = ?", (mail_id,))
    return _row(r[0], "attachments") if r else None


def unhandled() -> list[dict]:
    return [_row(r, "attachments") for r in _q("SELECT * FROM mails WHERE direction='in' AND handled=0 ORDER BY id")]


def mark_handled(mail_id: int, kind: str) -> None:
    with _lock:
        conn().execute("UPDATE mails SET handled=1, kind=? WHERE id=?", (kind, mail_id))
        conn().commit()


def mails(limit: int = 200) -> list[dict]:
    return [_row(r, "attachments") for r in _q("SELECT * FROM mails ORDER BY id DESC LIMIT ?", (limit,))]


# ---- records -----------------------------------------------------------------------------------------------

def put(id_: str, type_: str, status: str, data: dict) -> None:
    now = time.time()
    with _lock:
        conn().execute(
            "INSERT INTO records(id, type, status, data, created_at, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, data=excluded.data, updated_at=excluded.updated_at",
            (id_, type_, status, json.dumps(data, default=str), now, now))
        conn().commit()


def get(id_: str) -> dict | None:
    r = next(iter(_q("SELECT * FROM records WHERE id = ?", (id_,))), None)
    return _row(r, "data") if r else None


def update(id_: str, fn: Callable[[dict], tuple[str, dict] | None]) -> dict | None:
    """Read-modify-write under the lock. `fn(record)` returns (status, data), or None to leave it as it is."""
    with _lock:
        rec = get(id_)
        if rec is None:
            return None
        out = fn(rec)
        if out is None:
            return rec
        put(id_, rec["type"], out[0], out[1])
        return get(id_)


def records(type_: str | None = None, status: str | None = None, limit: int = 500) -> list[dict]:
    q, args = "SELECT * FROM records WHERE 1=1", []
    if type_:
        q, args = q + " AND type = ?", [*args, type_]
    if status:
        q, args = q + " AND status = ?", [*args, status]
    return [_row(r, "data") for r in _q(q + " ORDER BY updated_at DESC LIMIT ?", [*args, limit])]


def kv_get(k: str, default: str | None = None) -> str | None:
    r = next(iter(_q("SELECT v FROM kv WHERE k = ?", (k,))), None)
    return r["v"] if r else default


def kv_set(k: str, v: str) -> None:
    with _lock:
        conn().execute("INSERT INTO kv(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        conn().commit()


def _row(r: sqlite3.Row, json_field: str) -> dict:
    d = dict(r)
    if d.get(json_field):
        d[json_field] = json.loads(d[json_field])
    return d
