"""Anomaly watch: notice a market change before failed quotes pile up, say what changed and how to fix it.

5U changes the setup about once an hour, unannounced. A failed quote is the last signal and costs 100 points.
Detection is code over the register: free, every minute, no model. Diagnosis is one reasoning-model call per
new incident, through OpenAI directly. It answers no customer, so it is no quote and loses no points, and its
spend stays out of the cost 5U measures. Incidents are records of type `incident`. `make incidents` prints the
open ones as a brief that a teammate's coding agent can act on. Signals follow docs/research/watcher.md.

    cd backend && uv run python -m app.anomaly            # scan, diagnose new incidents, print the open ones
    cd backend && uv run python -m app.anomaly --close KEY
"""
import json
import os
import re
import sys
import time
from typing import Any

from app import kit, llm, store

OPS_MODEL = os.getenv("OPS_MODEL", "gpt-5.5")
SLOW_S = 75  # baseline: about 30 s after our mail
Z_MIN, BASE_N, MIN_BASE, SD_FLOOR = 3.0, 10, 3, 0.02  # price shocks: own last 10 deals, at least 3
FIRST_GAP = 0.15  # first live price this far off the sheet: the sheet is likely stale
AMOUNT = re.compile(r"(\d[\d,.]*\d)\s*(EUR|USD|GBP|CHF|CNY|JPY)\b|\b(EUR|USD|GBP|CHF|CNY|JPY)\s*(\d[\d,.]*\d)")
GOOD = {"accepted", "correct", "ok", "open", "pending", "won", "booked", "scored"}
# 5U booth, Sat 15:50: news play no role, but customers' replies may name problems that point to a disruption.
TROUBLE = re.compile(
    r"strike|delay|congest|closed|shortage|backlog|disrupt|cancel|embargo|storm|volcan|outage|problem|issue|"
    r"capacity|surcharge|stuck|"
    r"streik|verspät|verzöger|gesperrt|engpass|ausfall|stau|"
    r"sciopero|ritard|chius|blocc|carenza|"
    r"huelga|retras|cerrad|bloque|escasez|"
    r"grève|greve|retard|fermé|pénurie", re.I)
DESKS = {"ratedesk@hackloop.mail", "tracking@hackloop.mail"}
STATUS = re.compile(r"\b(410|422|429|500|502|503|504)\b")


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def price_shocks(deals: list[dict]) -> list[dict]:
    """A carrier's live price (portal, mail) against its own sheet price on the same deal: the ratio removes
    weight and lane, so every deal is one point on the carrier's series. A shock is a jump against the
    carrier's own earlier points (z >= Z_MIN, method from trend_scout sim/shocks.py), or, before enough
    points exist, a first live price far off the sheet (a new tariff, catalog 1)."""
    series: dict[str, list[tuple[float, float, str]]] = {}
    for rec in sorted(deals, key=lambda r: r.get("updated_at") or 0):
        offers = [o for o in rec["data"].get("offers", []) if o.get("leg") == "air"]
        sheet = {o["carrier"]: float(o["total"]) for o in offers if o.get("source") == "sheet"}
        for o in offers:
            if o.get("source") in ("portal", "email") and sheet.get(o["carrier"]):
                series.setdefault(o["carrier"], []).append((float(o["total"]) / sheet[o["carrier"]],
                                                             float(o["total"]), rec["id"]))
    out = []
    for carrier, pts in series.items():
        for i, (ratio, total, deal) in enumerate(pts):
            base = [p[0] for p in pts[max(0, i - BASE_N):i]]
            if len(base) >= MIN_BASE:
                mu = sum(base) / len(base)
                sd = max((sum((b - mu) ** 2 for b in base) / len(base)) ** 0.5, SD_FLOOR)
                z = (ratio - mu) / sd
                if abs(z) >= Z_MIN:
                    out.append({"carrier": carrier, "deal": deal, "ratio": round(ratio, 3), "z": round(z, 1),
                                "base_ratio": round(mu, 3), "total": total})
            elif i == 0 and abs(ratio - 1) >= FIRST_GAP:
                out.append({"carrier": carrier, "deal": deal, "ratio": round(ratio, 3), "z": None,
                            "base_ratio": 1.0, "total": total})
    return out


def signals(mails: list[dict], events: list[dict], board: dict | None, deals: list[dict] = ()) -> list[dict]:
    """Everything that differs from the baseline, one entry per (kind, subject). Pure: tests feed it data."""
    out: dict[str, dict] = {}

    def hit(key: str, change: str, what: str, evidence: Any) -> None:
        s = out.setdefault(key, {"key": key, "change": change, "what": what, "evidence": []})
        if len(s["evidence"]) < 5:
            s["evidence"].append(evidence)

    w = kit.world()
    by_id = {m["id"]: m for m in mails}
    for m in mails:
        if m["direction"] != "in":
            continue
        carrier = w.carrier_by_email(m["sender"].lower())
        if carrier is None:
            words = sorted({x.lower() for x in TROUBLE.findall(m["body"] or "")})
            if m["sender"].lower() not in DESKS and words:
                hit(f"customer:{m['root']}", "15", f"customer {m['sender']} mentions {', '.join(words)}",
                    {"mail": m["id"], "from": m["sender"], "subject": m["subject"], "body": (m["body"] or "")[:800]})
            continue
        body, ev = m["body"] or "", {"mail": m["id"], "from": m["sender"], "subject": m["subject"],
                                     "body": (m["body"] or "")[:600]}
        asked = by_id.get(m.get("in_reply_to") or -1)
        t_in, t_out = _ts(m.get("received_at")), _ts(asked.get("received_at")) if asked else None
        if t_in and t_out and t_in - t_out > SLOW_S:
            hit(f"slow:{m['sender']}", "8", f"{carrier.name} answered {t_in - t_out:.0f} s after our request",
                {**ev, "delay_s": round(t_in - t_out)})
        currencies = {a[1] or a[2] for a in AMOUNT.findall(body)} - {"EUR", ""}
        for cur in currencies:
            hit(f"currency:{cur}", "7", f"carrier prices in {cur}", ev)
        if re.search(r"we need|please provide|missing|to quote", body, re.I) and not AMOUNT.search(body):
            hit(f"askback:{m['sender']}", "9", f"{carrier.name} asks back instead of quoting", ev)
        elif re.search(r"per kg|/kg|per kilo", body, re.I) and asked:
            hit(f"perkg:{m['sender']}", "10", f"{carrier.name} quotes per kg", ev)
        if m.get("attachments") and not m.get("in_reply_to"):
            hit(f"tariff:{m['sender']}", "1", f"{carrier.name} sent a file nobody asked for (tariff?)",
                {**ev, "files": [a.get("filename") if isinstance(a, dict) else a for a in m["attachments"]]})
        if re.search(r"valid from|effective|gültig ab|from 1 dec|december", body, re.I) and m.get("attachments"):
            hit(f"validity:{m['sender']}", "2", f"{carrier.name} tariff may not be valid yet", ev)
    for e in events:
        text = e["summary"]
        if e["kind"] == "error":
            code = STATUS.search(text)
            if code:
                hit(f"http:{code.group(1)}:{e['agent']}", {"503": "3", "429": "5", "410": "6"}.get(code.group(1), "0"),
                    f"{code.group(1)} errors in {e['agent']}", {"event": e["id"], "summary": text[:300]})
        if "DIRECT (gateway down)" in text:
            hit("gateway-down", "0", "the 5U gateway failed, calls went to OpenAI directly (no time points)",
                {"event": e["id"], "summary": text[:200]})
    for s in price_shocks(list(deals)):
        hit(f"price:{s['carrier']}", "1", f"{s['carrier']} live price at {s['ratio']}x its sheet "
            f"(usual {s['base_ratio']}x)", s)
    for r in (board or {}).get("requests", []):
        verdict = str(r.get("verdict") or "").lower()
        if verdict and verdict not in GOOD:
            reason = re.sub(r"\W+", "-", str(r.get("reason") or r.get("reason_code") or verdict).lower())[:40]
            hit(f"board:{reason}", "13", f"5U scored a round {verdict}: {r.get('reason') or ''}"[:200], r)
    return list(out.values())


def diagnose(s: dict) -> dict:
    """One reasoning call: which change, how sure, the smallest fix. Never on the gateway (no quote)."""
    schema = llm.strict({
        "change": {"type": "string", "description": "catalog number, 0 if none fits"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "what_changed": {"type": "string"},
        "tell_apart": {"type": ["string", "null"], "description": "what would rule out the second-best reading"},
        "fix": {"type": "string", "description": "the smallest change that makes quotes right again"},
        "where": {"type": "string", "description": "file, prompt, config, or 'ask 5U'"},
        "urgent": {"type": "boolean", "description": "true if quotes fail or lose points until fixed"},
    })
    c = llm.direct() or llm.client()
    t = time.time()
    try:
        res = c.chat.completions.create(
            model=OPS_MODEL, reasoning_effort="high",
            messages=[{"role": "system", "content": llm.prompt("ops")},
                      {"role": "user", "content": json.dumps(s, ensure_ascii=False, default=str)}],
            response_format={"type": "json_schema", "json_schema": {"name": "diagnosis", "strict": True,
                                                                     "schema": schema}})
    except Exception as e:  # diagnosis is help, never a blocker: the signal stands without it
        store.log("ops", "error", f"diagnosis failed: {e!r}"[:300], run_id="ops")
        return {"error": repr(e)[:300]}
    u = res.usage
    tin, tout = getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0
    store.log("ops", "llm", f"{OPS_MODEL} [diagnosis] {time.time() - t:.1f}s off-gateway", None, run_id="ops",
              tokens_in=tin, tokens_out=tout, cost_usd=llm.cost(OPS_MODEL, tin, 0, tout))
    return json.loads(res.choices[0].message.content or "{}")


def check(diagnose_new: bool = True) -> list[dict]:
    """Scan the register; open an incident per new signal, diagnose it once. Returns the incidents opened."""
    board = json.loads(store.kv_get("board_me") or "null")
    found = signals(store.mails(500), store.events(limit=500), board, store.records("deal", limit=300))
    opened = []
    for s in found:
        rid = "incident-" + re.sub(r"[^\w-]+", "-", s["key"])[:80]
        old = store.get(rid)
        if old and old["status"] == "open":
            continue
        if old and old["status"] == "closed" and old["data"].get("evidence") == s["evidence"]:
            continue  # closed and nothing new
        d = {**s, "at": time.time(), "diagnosis": diagnose(s) if diagnose_new else None}
        store.put(rid, "incident", "open", d)
        store.log("watcher", "anomaly", f"{s['what']}"[:300], {"incident": rid, "diagnosis": d["diagnosis"]},
                  run_id="ops")
        opened.append({"id": rid, **d})
    return opened


def close(key: str) -> None:
    rid = key if key.startswith("incident-") else "incident-" + re.sub(r"[^\w-]+", "-", key)[:80]
    store.update(rid, lambda r: ("closed", r["data"]))


def brief(incidents: list[dict]) -> str:
    """Open incidents as a task for a coding agent: evidence first, the model's reading second."""
    if not incidents:
        return "No open incidents."
    lines = []
    for r in incidents:
        d, g = r["data"], r["data"].get("diagnosis") or {}
        lines += [f"## {r['id']}: {d['what']}", f"catalog change {g.get('change', d['change'])}, "
                  f"confidence {g.get('confidence', '?')}, urgent {g.get('urgent', '?')}",
                  f"- what changed: {g.get('what_changed', '-')}", f"- fix: {g.get('fix', '-')} ({g.get('where', '-')})",
                  f"- tell apart: {g.get('tell_apart') or '-'}", "- evidence:"]
        lines += [f"  - {json.dumps(e, ensure_ascii=False, default=str)[:400]}" for e in d["evidence"]]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    kit.load()
    if len(sys.argv) > 2 and sys.argv[1] == "--close":
        close(sys.argv[2])
    else:
        check()
    print(brief(store.records("incident", "open")))
