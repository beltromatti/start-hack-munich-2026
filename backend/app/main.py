"""HTTP API for the sessions UI, and the forwarder loop when WORKER=1.

Run: uv run uvicorn app.main:app --port 8000   (make api / make live)
"""
import base64
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
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

_PASSWORD = os.getenv("UI_PASSWORD", "")


@app.middleware("http")
async def team_only(request: Request, call_next):
    """On a public address (the server), the UI and the API ask for the team password (browser login box).
    /api/health stays open for health checks. No UI_PASSWORD set (a laptop): open, as before."""
    if _PASSWORD and request.url.path != "/api/health":
        auth = request.headers.get("authorization", "")
        try:
            given = base64.b64decode(auth.split(" ", 1)[1]).decode().split(":", 1)[1] if auth.startswith("Basic ") else ""
        except Exception:
            given = ""
        if not hmac.compare_digest(given, _PASSWORD):
            return Response("Team only", status_code=401, headers={"WWW-Authenticate": 'Basic realm="START Milan"'})
    return await call_next(request)


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
                    "needs_person": d.get("person_needed"),  # legacy session history
                    "browser_activity": d.get("browser_activity"),
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
    return {**r, "mails": store.thread(root), "carrier_mails": store.carrier_mails(deal_id),
            "events": store.events(run_id=deal_id), "usage": store.usage(deal_id),
            "session": {"status": s["status"], "items": s["data"].get("items", [])} if s else None}


@app.get("/api/mails/{mail_id}/attachments/{attachment_id}")
def attachment(mail_id: int, attachment_id: int) -> Response:
    """The original file, as it came (a PDF, a Word letter, a voice message, a scan): from 5U, through us."""
    m = store.mail(mail_id)
    a = next((x for x in (m or {}).get("attachments") or [] if str(x.get("id")) == str(attachment_id)), None)
    if not a:
        raise HTTPException(404)
    from .fiveu import FiveU
    api = forwarder.api if forwarder else FiveU()
    name = (a.get("filename") or "attachment").replace('"', "")
    return Response(api.attachment(mail_id, attachment_id), media_type=a.get("content_type") or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


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


@app.get("/api/operator")
def operator_mode() -> dict:
    """Observer alerts only. Browser work is autonomous, including when alerts are off."""
    needed = []
    for r in store.records("deal"):
        pm = r["data"].get("portal_missing") or {}
        if r["status"] not in ("new", "pricing") or not pm.get("airlines"):
            continue
        req = r["data"].get("request") or {}
        needed.append({"deal": r["id"], "subject": r["data"].get("subject"), "customer": r["data"].get("customer"),
                       "received_at": r["data"].get("received_at"), "preference": r["data"].get("preference"),
                       # what 5U's portal form asks for, ready to copy: origin, destination, gross weight, volume
                       "origin": req.get("origin"), "destination": req.get("destination"),
                       "gross_kg": req.get("weight_kg"), "volume_cbm": req.get("volume_cbm"),
                       "chargeable_kg": req.get("chargeable_kg"), **pm})
    return {"on": store.kv_get("operator_on", "1") == "1", "autonomous": True, "needed": needed}


@app.post("/api/operator")
def set_operator_mode(payload: dict) -> dict:
    store.kv_set("operator_on", "1" if payload.get("on") else "0")
    store.log("human", "decision", f"observer alerts {'on' if payload.get('on') else 'off'}")
    return operator_mode()


@app.post("/api/deals/{deal_id}/portal_rate")
def portal_rate(deal_id: str, payload: dict) -> dict:
    """A person enters a rate they read on 5U's portal page (airline, total EUR, transit days, rate_id)."""
    from .forwarder import add_portal_page_rate, read_portal_page
    if payload.get("pasted") is not None:  # the page's result as copied: read by code, shown back before it is added
        read = read_portal_page(payload["pasted"])
        if payload.get("dry"):
            return {"read": read}
        payload = {**payload, **{k: v for k, v in read.items() if v and not payload.get(k)}}
    out = add_portal_page_rate(deal_id, payload.get("airline") or "", payload.get("total"), payload.get("days"),
                               payload.get("rate_id"), payload.get("weight_kg"), payload.get("who") or "operator")
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out


@app.get("/api/portal/{deal_id}/shot")
def portal_shot(deal_id: str) -> Response:
    """The shared browser's page for this deal, live, for the person in the deal's conversation."""
    import httpx
    try:
        r = httpx.get(f"{settings.browser_base_url}/pages/{deal_id}/shot", timeout=10, trust_env=False)
    except Exception:
        raise HTTPException(503, "the shared browser is not running")
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text[:200])
    return Response(r.content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/portal/{deal_id}/{what}")
def portal_input(deal_id: str, what: str, payload: dict) -> dict:
    """The person's shared page and input. Opening it never exposes an arbitrary URL proxy."""
    import httpx
    if what not in ("open", "click", "type", "scroll", "focus"):
        raise HTTPException(404)
    if not store.get(deal_id):
        raise HTTPException(404, "no such deal")
    path = f"/pages/{deal_id}" if what == "open" else f"/pages/{deal_id}/{what}"
    if what == "open":
        payload = {"reload": bool(payload.get("reload"))}
    try:
        r = httpx.post(f"{settings.browser_base_url}{path}", json=payload, timeout=30, trust_env=False)
    except httpx.HTTPError:
        raise HTTPException(503, "the shared browser is not running")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:200])
    # The UI needs no page text here; the agent reads rates through its existing browser tool.
    return {"ok": True} if what == "open" else r.json()


@app.post("/api/deals/{deal_id}/person_answer")
def person_answer(deal_id: str, payload: dict) -> dict:
    """The person's answer to the agent's ask_person (kind answer)."""
    text = (payload.get("text") or "").strip()
    r = store.get(deal_id)
    if not r or not (r["data"].get("person_needed")) or not text:
        raise HTTPException(400, "nothing asked, or an empty answer")
    store.update(deal_id, lambda x: (x["status"], {**x["data"], "person_needed": {**x["data"]["person_needed"], "answer": text}}))
    store.log("human", "decision", f"answer to the agent: {text[:200]}", run_id=deal_id)
    return {"ok": True}


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



# Last: the UI mount at "/" would shadow any route added after it.
# The sessions UI, built (frontend/dist): served by the same process on a server (Docker), so one port is enough.
_dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
