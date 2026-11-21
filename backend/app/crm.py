"""The CRM as a read-only projection of the register: requests (one per 5U round), customers, carriers, points.

Nothing here writes, and nothing decides. It reads what the forwarder already stores (mails both ways, deals,
board snapshots) and lays it out for the human (the CRM pages) and for the agent (cards through the crm tool).
Where a deal record exists (the live machine) its facts win. On a machine with only mails (a register filled from
the 5U backup) the facts come from the mails, and what neither holds stays None. Totals shown here are the totals
our quote mail carried, never a new computation.

Points per round: `/v1/board/me` gives every request its points per kind (accuracy, time, cost, tracking, humanity,
booking). Those are the round's points. Board deltas (a delta with exactly one new verdict) are the fallback for a
snapshot without them, and the series over time feeds the race chart.
"""
import json
import re
import time
from datetime import datetime
from statistics import median
from typing import Any

from . import kit, store

TEAM = "start-milan"
# Full marks per kind (brief: accuracy 45, cost 40, time 15, humanity 10, tracking 10). Booking pays 0 so far.
MAX = {"accuracy": 45.0, "time": 15.0, "cost": 40.0, "tracking": 10.0, "humanity": 10.0}
FINAL = {"accepted", "rejected", "no answer", "voided"}
RATEDESK, TRACKING = "ratedesk@hackloop.mail", "tracking@hackloop.mail"
IATA = re.compile(r"\b([A-Z]{3})\b")
NOT_IATA = {"EUR", "USD", "CBM", "ETA", "RFQ", "DDP", "EXW", "FCA", "DAP", "GMBH", "LTD"}
KG = re.compile(r"(\d[\d.,]*)\s*kg\b", re.I)
CBM = re.compile(r"(\d[\d.,]*)\s*(?:cbm|m3|m³)", re.I)
EUR = re.compile(r"(\d[\d.,]*\d)\s*EUR", re.I)
TOTAL = re.compile(r"Total:\s*(\d[\d.,]*\d)\s*EUR", re.I)
POSTCODE = re.compile(r"\b(\d{5})\b")
DECLINE = re.compile(r"do not serve|cannot offer|not able to|no capacity|unable to", re.I)
CLOSING = re.compile(r"^((kind|best|warm|many|viele|beste|liebe|freundliche)\s+)?(regards|wishes|grüße|gruesse|"
                     r"greetings|saluti|cordiali saluti)\b|^(thanks|thank you|best|cheers|danke|grazie|sincerely|"
                     r"mit freundlichen)\b", re.I)
QUOTED = re.compile(r"^-{3,}\s*original message|^on .+ wrote:$|^am .+ schrieb", re.I | re.M)
LANE = re.compile(r"Rate request ([A-Z]{3})-([A-Z]{3}) (\d+(?:\.\d+)?) kg")
ZONE = re.compile(r"Pickup quote (?:zone )?(\d+)")
# What makes a request harder than a plain one, for the people reading the CRM (5U adds one kind every few rounds).
# A diagnostic shown to the team only: the agent never sees it and nothing decides on it.
TRAITS = {
    "lots": re.compile(r"^\s*Lot \d", re.I | re.M),
    "attachment": re.compile(r"attach", re.I),
    "dangerous goods": re.compile(r"dangerous|\bDG\b|\bUN\s?\d{4}\b", re.I),
    "import": re.compile(r"\bimport", re.I),
    "own delivery": re.compile(r"no pickup|deliver the goods|we.ll deliver", re.I),
    "forwarded chain": re.compile(r"original message|^(RE|FW|AW|WG):", re.I | re.M),
    "earliest arrival": re.compile(r"earliest", re.I),
}
TRANSIT = re.compile(r"(\d+(?:\.\d+)?)\s*(day|days|hour|hours|h)\b", re.I)
REF = re.compile(r"\b((?:R|TRK)-[A-Za-z0-9-]+)")


def _ts(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()


def _num(s: str | None) -> float | None:
    """'1,233' 1233, '3230.03' 3230.03, '1.233,50' 1233.5."""
    if not s:
        return None
    if re.search(r",\d{1,2}$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _f(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _days(text: str) -> float | None:
    """'1-day transit', 'Transit: 3 days', 'Pickup time: 11 hours' as days."""
    m = TRANSIT.search(text or "")
    if not m:
        return None
    v = float(m.group(1))
    return round(v / 24, 2) if m.group(2).lower().startswith("h") else v


def _first(rx: re.Pattern, text: str) -> float | None:
    m = rx.search(text or "")
    return _num(m.group(1)) if m else None


def _w() -> kit.World:
    """The start kit, loaded from disk when the API runs without the forwarder."""
    return kit.world() if kit.world().carriers else kit.load()


def _carrier(email: str):
    return _w().carrier_by_email(email)


def signature(body: str) -> dict:
    """Who signed a mail: the lines after the closing ('Kind regards'), else the last two lines.
    A forwarded or quoted mail below the signature is cut off first. Person, title, company."""
    body = QUOTED.split(body or "")[0]
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    tail: list[str] = []
    for i in range(len(lines) - 1, max(-1, len(lines) - 7), -1):
        if CLOSING.match(lines[i]):
            tail = lines[i + 1:]
            break
    if not tail:
        tail = lines[-2:]
    tail = [l for l in tail if "@" not in l][:4]
    if not tail:
        return {}
    if len(tail) == 1:
        return {"company": tail[0]}
    return {"person": tail[0], "title": tail[1] if len(tail) > 2 else None, "company": tail[-1]}


def _all_mails() -> list[dict]:
    return [store._row(r, "attachments") for r in store._q("SELECT * FROM mails ORDER BY id")]


def _board_snaps() -> list[dict]:
    snaps = [r["data"] for r in store.records("board", limit=100000)]
    return sorted((s for s in snaps if s.get("me")), key=lambda s: _ts(s.get("at")) or 0)


def points_timeline() -> dict:
    """Our total over time, every team's total per snapshot, and points per round where a delta isolates it."""
    per_round: dict[int, float] = {}
    batches, series = [], []
    prev = None
    for s in _board_snaps():
        at, me = _ts(s["at"]), s["me"]
        total = float(me.get("total") or 0)
        ranking = (s.get("public") or {}).get("ranking", [])
        series.append({"at": at, "total": total, "rank": me.get("rank"),
                       "teams": {r["name"]: r["total"] for r in ranking}})
        if prev:
            delta = round(total - prev["total"], 2)
            before = {r["round_no"]: r.get("verdict") for r in prev["requests"]}
            new = [r["round_no"] for r in me.get("requests", [])
                   if r.get("verdict") in FINAL and before.get(r["round_no"]) not in FINAL]
            if delta and len(new) == 1:
                per_round[new[0]] = delta
            elif delta:
                batches.append({"at": at, "delta": delta, "rounds": new})
        prev = {"total": total, "requests": me.get("requests", [])}
    return {"series": series, "per_round": per_round, "batches": batches}


def _latest_board() -> tuple[dict, dict]:
    snaps = _board_snaps()
    if snaps:
        return snaps[-1]["me"], snaps[-1].get("public") or {}
    return (json.loads(store.kv_get("board_me") or "null") or {}), (json.loads(store.kv_get("board") or "null") or {})


def _is_rfq(m: dict) -> bool:
    s = m["sender"].lower()
    return (m["direction"] == "in" and m["root"] == m["id"] and s not in (RATEDESK, TRACKING) and not _carrier(s)
            and not re.match(r"^booking\s+\S+\s+confirmed", m["subject"] or "", re.I))


def traits(subject: str, body: str) -> list[str]:
    """The harder parts of a request: what TRAITS finds, plus a pickup with no postcode in the customer's own text."""
    text = f"{subject}\n{body}"
    own = QUOTED.split(body)[0]
    out = [k for k, r in TRAITS.items() if r.search(text)]
    if re.search(r"pickup|truck", own, re.I) and "own delivery" not in out and not POSTCODE.search(own):
        out.append("no postcode")
    return out


def cases() -> list[dict]:
    """One row per customer request (a 5U round): the request, what we did, what 5U said. Newest first.
    Shaped like the dashboard's Case (frontend/src/crm), so its views run on real data.
    Lane, chargeable weight and pickup zone come from our own carrier requests in the round ("Rate request
    CGN-DFW 2101 kg", "Pickup quote zone 51 to CGN"): exact, where the customer's prose is not."""
    mails = _all_mails()
    me, _ = _latest_board()
    rounds = [(_ts(r["sent_at"]), r) for r in me.get("requests", [])]
    pts = points_timeline()["per_round"]
    deals = {r["data"].get("root"): r for r in store.records("deal", limit=100000) if r["data"].get("root")}
    by_root: dict[int, list[dict]] = {}
    for m in mails:
        by_root.setdefault(m["root"], []).append(m)
    tracking = [m for m in mails if m["sender"].lower() == TRACKING and m["root"] == m["id"]]
    w = _w()
    origins = w.origins()
    rfqs = list(filter(_is_rfq, mails))
    starts = sorted(_ts(m["received_at"]) or 0 for m in rfqs)
    out = []
    for m in rfqs:
        start = _ts(m["received_at"]) or 0
        end = min([t for t in starts if t > start] + [start + 360])
        rnd = next((r for t, r in rounds if abs(t - start) < 5), {})
        thread = by_root.get(m["root"], [])
        ours = [x for x in thread if x["direction"] == "out" and x["recipient"].lower() == m["sender"].lower()]
        quote = next((x for x in ours if TOTAL.search(x["body"])), None)
        first = ours[0] if ours else None
        deal = deals.get(m["root"])
        d = deal["data"] if deal else {}
        req = d.get("request") or {}
        text = f"{m['subject']}\n{QUOTED.split(m['body'])[0]}"
        sig = signature(m["body"])
        in_window = lambda x: start <= (_ts(x["received_at"]) or 0) < end
        asked = [x for x in mails if x["direction"] == "out" and in_window(x)
                 and (_carrier(x["recipient"]) or x["recipient"].lower() == RATEDESK)
                 and not re.search(r"booking", x["subject"] or "", re.I)]
        carrier_roots = {x["root"] for x in asked}
        replies = [x for x in mails if x["direction"] == "in" and x["root"] != m["root"] and
                   (x["root"] in carrier_roots or (x["sender"].lower() == RATEDESK and in_window(x)))]
        lane_m = next((LANE.search(x["subject"]) for x in asked if LANE.search(x["subject"])), None)
        zone_m = next((ZONE.search(x["subject"]) for x in asked if ZONE.search(x["subject"])), None)
        bids = []
        for x in replies:
            c = _carrier(x["sender"])
            declined = bool(DECLINE.search(x["body"]))
            bids.append({"carrier": c.name if c else "Rate desk", "email": x["sender"].lower(),
                         "kind": c.kind if c else "ratedesk", "source": "email" if c else "portal",
                         "total": None if declined else _first(EUR, x["body"]), "declined": declined,
                         "transitDays": _days(x["body"]), "ref": (REF.search(x["body"]) or [None, None])[1]
                         if REF.search(x["body"]) else None, "subject": x["subject"],
                         "at": round((_ts(x["received_at"]) or start) - start)})
        quote_at = round(_ts(quote["received_at"]) - start) if quote else None
        first_at = round(_ts(first["received_at"]) - start) if first else None
        quote_total = (d.get("quote") or {}).get("amount") or (_first(TOTAL, quote["body"]) if quote else None)
        verdict = rnd.get("verdict") or ("quoted" if quote else "open")
        kg = _f(req.get("weight_kg")) or _first(KG, text)
        cbm = _f(req.get("volume_cbm")) or _first(CBM, text)
        dest = req.get("destination") or (lane_m.group(2) if lane_m else None)
        track_rows = []
        for t in tracking:
            if not (dest and dest in t["subject"] and kg and f"{int(kg)} kg" in t["subject"]):
                continue
            ans = next((x for x in by_root.get(t["root"], []) if x["direction"] == "out"), None)
            track_rows.append({"asked_at": _ts(t["received_at"]), "subject": t["subject"],
                               "answered_s": round(_ts(ans["received_at"]) - _ts(t["received_at"])) if ans else None,
                               "answer": ans["body"] if ans else None})
        asked_back = first is not None and first is not quote and (quote is None or first["id"] < quote["id"])
        slow = quote_at is not None and quote_at > 45
        open_tracking = any(r["answered_s"] is None for r in track_rows)
        bucket = ("red" if verdict in ("rejected", "no answer") else
                  "yellow" if slow or open_tracking or verdict in ("pending", "open") else "green")
        reason = rnd.get("reason") or ("no quote within the 6 minutes" if verdict == "no answer" else
                                       f"asked back first, quote after {quote_at} s" if slow and asked_back else
                                       f"quote after {quote_at} s" if slow else
                                       "tracking reply not found" if open_tracking else None)
        lane = {x["id"]: x for x in [*thread, *asked, *replies]}
        out.append({
            "id": deal["id"] if deal else f"rfq-{m['root']}", "root": m["root"], "round": rnd.get("round_no"),
            "start": start, "customer": sig.get("company") or m["sender"].split("@")[0], "contact": sig.get("person"),
            "contactTitle": sig.get("title"), "email": m["sender"].lower(), "subject": m["subject"],
            "origin": req.get("origin") or (lane_m.group(1) if lane_m else None),
            "destination": dest, "weightKg": kg, "volumeCbm": cbm,
            "chargeableKg": _f(req.get("chargeable_kg")) or (float(lane_m.group(3)) if lane_m else None),
            "pieces": req.get("pieces"), "commodity": req.get("commodity"), "readyDate": req.get("ready_date"),
            "wants": d.get("preference") or ("fastest" if re.search(r"fastest|schnell|urgent|express|veloce", text, re.I)
                                             else "cheapest"),
            "pickupZone": zone_m.group(1) if zone_m else None,
            "bucket": bucket, "reason": reason, "bids": bids, "quoteTotal": quote_total, "quoteAt": quote_at,
            "firstReplyAt": first_at, "askedBack": asked_back,
            "firstReply": first["body"] if asked_back else None, "quoteText": quote["body"] if quote else None,
            "costUsd": store.usage(deal["id"])["cost_usd"] if deal else None,
            "verdict": verdict, "booked": rnd.get("booked"),
            "points": round(sum(rnd["points"].values()), 2) if rnd.get("points") else pts.get(rnd.get("round_no")),
            "pointsBy": rnd.get("points") or {}, "traits": traits(m["subject"] or "", m["body"] or ""),
            "tracking": track_rows,
            "mails": [{"id": x["id"], "t": round((_ts(x["received_at"]) or start) - start), "direction": x["direction"],
                       "from": x["sender"], "to": x["recipient"], "subject": x["subject"], "body": x["body"]}
                      for x in sorted(lane.values(), key=lambda x: x["id"])],
        })
    return sorted(out, key=lambda c: c["start"], reverse=True)


def rows(cs: list[dict] | None = None) -> list[dict]:
    """One flat row per request with every variable we hold, oldest first: the table for correlations (Jan,
    15:42: "a long list of every order ... so that after 24 hours we can do correlation analysis"). Only facts and
    counts from cases(); nothing here is a judgement."""
    out, seen = [], {}
    for c in sorted(cs if cs is not None else cases(), key=lambda c: c["start"]):
        seen[c["email"]] = seen.get(c["email"], 0) + 1
        priced = [b["total"] for b in c["bids"] if b["total"] is not None and b["kind"] != "trucker"]
        ready = _ts(c.get("readyDate")) if c.get("readyDate") else None
        out.append({
            "round": c["round"], "received_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(c["start"])),
            "hour_utc": time.gmtime(c["start"]).tm_hour, "customer": c["customer"], "email": c["email"],
            "nth_request_of_customer": seen[c["email"]], "origin": c["origin"], "destination": c["destination"],
            "door_to_port": c["pickupZone"] is not None, "pickup_zone": c["pickupZone"], "weight_kg": c["weightKg"],
            "volume_cbm": c["volumeCbm"], "chargeable_kg": c["chargeableKg"], "pieces": c.get("pieces"),
            "commodity": c.get("commodity"), "ready_in_days": round((ready - c["start"]) / 86400, 1) if ready else None,
            "wants": c["wants"], "traits": "; ".join(c["traits"]), "carriers_answered": len(c["bids"]),
            "carriers_declined": sum(b["declined"] for b in c["bids"]),
            "cheapest_air_bid": min(priced) if priced else None, "quote_total": c["quoteTotal"],
            "first_reply_s": c["firstReplyAt"], "quote_s": c["quoteAt"], "asked_back": c["askedBack"],
            "model_cost_usd": c["costUsd"], "verdict": c["verdict"], "reason": c["reason"], "booked": c["booked"],
            "points": c["points"], **{f"points_{k}": v for k, v in (c.get("pointsBy") or {}).items()},
            "tracking_asked": len(c["tracking"]),
            "tracking_answered": sum(t["answered_s"] is not None for t in c["tracking"]),
        })
    return out


def customers(cs: list[dict] | None = None) -> list[dict]:
    """One card per customer: who signs, what they asked over time, what came of it."""
    cards: dict[str, dict] = {}
    for c in sorted(cs if cs is not None else cases(), key=lambda c: c["start"]):
        card = cards.setdefault(c["email"], {"email": c["email"], "company": c["customer"], "contact": None,
                                             "title": None, "requests": []})
        card["contact"] = c["contact"] or card["contact"]
        card["title"] = c["contactTitle"] or card["title"]
        card["requests"].append({k: c[k] for k in ("round", "start", "origin", "destination", "weightKg", "volumeCbm",
                                                   "wants", "quoteTotal", "quoteAt", "verdict", "booked", "points")})
    for card in cards.values():
        rs = card["requests"]
        card.update(n=len(rs), accepted=sum(r["verdict"] == "accepted" for r in rs),
                    booked=sum(bool(r["booked"]) for r in rs), last=rs[-1]["start"])
    return sorted(cards.values(), key=lambda c: c["last"], reverse=True)


def carriers(cs: list[dict] | None = None) -> list[dict]:
    """One card per carrier on the kit list: how often we asked, how it answered, where it said no."""
    stats = {c.email.lower(): {"email": c.email.lower(), "name": c.name, "kind": c.kind, "serves": c.serves,
                               "asked": 0, "replied": 0, "priced": 0, "declined": [], "_s": []}
             for c in _w().carriers}
    for c in cs if cs is not None else cases():
        for x in c["mails"]:
            if x["direction"] == "out" and x["to"].lower() in stats:
                stats[x["to"].lower()]["asked"] += 1
        for b in c["bids"]:
            s = stats.get(b["email"].lower())
            if not s:
                continue
            s["replied"] += 1
            s["_s"].append(b["at"])
            if b["declined"]:
                s["declined"].append(c["destination"])
            elif b["total"]:
                s["priced"] += 1
    out = []
    for s in stats.values():
        rs = s.pop("_s")
        out.append({**s, "reply_rate": round(min(1, s["replied"] / s["asked"]), 2) if s["asked"] else None,
                    "median_reply_s": median(rs) if rs else None})
    return sorted(out, key=lambda s: (-s["asked"], s["name"]))


def losses(cs: list[dict] | None = None) -> dict:
    """Where points go: rounds without a quote or rejected, slow quotes, tracking we left open, rounds below best."""
    cs = cs if cs is not None else cases()
    tl = points_timeline()
    _, pub = _latest_board()
    us = next((r for r in pub.get("ranking", []) if r.get("name") == TEAM), {})
    acc = [c for c in cs if c["verdict"] == "accepted" and c["pointsBy"]]
    # A kind counts as settled once 5U has paid it for any later round: humanity and tracking come in batches, cost
    # hourly. Before that, a missing kind is pending, not lost.
    last = {k: max((c["round"] or 0 for c in acc if k in c["pointsBy"]), default=0) for k in MAX}
    by_kind = {k: {"lost": round(sum(MAX[k] - c["pointsBy"].get(k, 0.0) for c in acc if (c["round"] or 0) <= last[k]
                                     and (k != "tracking" or c["booked"])), 2),
                   "rounds": [c["round"] for c in acc if (c["round"] or 0) <= last[k] and c["pointsBy"].get(k, 0.0) < MAX[k]
                              and (k != "tracking" or c["booked"])]}
               for k in MAX}
    full = sum(MAX.values())
    return {
        "total": us.get("total"), "rank": us.get("rank"), "answered": us.get("answered"),
        "accepted": us.get("accepted"), "human": us.get("human"), "bookings": us.get("bookings"),
        "rules": pub.get("rules"), "rounds_sent": (pub.get("overview") or {}).get("rounds_sent"),
        "missed": [{"round": c["round"], "at": c["start"], "subject": c["subject"]} for c in cs if c["verdict"] == "no answer"],
        "rejected": [{"round": c["round"], "reason": c["reason"]} for c in cs if c["verdict"] == "rejected"],
        "slow": [{"round": c["round"], "quoteAt": c["quoteAt"]} for c in cs if (c["quoteAt"] or 0) > 120],
        "tracking_asked": sum(len(c["tracking"]) for c in cs),
        "tracking_unanswered": sum(1 for c in cs for t in c["tracking"] if t["answered_s"] is None),
        "per_round_points": {str(c["round"]): c["points"] for c in cs if c["points"] is not None},
        "by_kind": by_kind, "round_max": full, "missed_lost": round(full * len([c for c in cs if c["verdict"] == "no answer"]), 2),
        "batches": tl["batches"],
    }
