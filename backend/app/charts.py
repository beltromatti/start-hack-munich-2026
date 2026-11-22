"""Charts over the register, for the desk: the assistant chooses what to look at (a measure, by what, which
shipments), this module computes every number. One implementation for the chat and for charts a person pins to
their Efficiency page, so a pinned chart is the same question asked again on fresh data.
"""
import math
from collections import defaultdict
from datetime import datetime

from . import economics, store

GROUPS = ["customer", "route", "origin", "destination", "airline", "status", "preference", "day", "hour"]
MEASURES = {  # name: (unit, how the values of one group combine)
    "shipments": ("shipments", "count"), "bookings": ("bookings", "sum"), "booking_rate": ("%", "rate"),
    "quoted_eur": ("EUR", "sum"), "booked_eur": ("EUR", "sum"), "average_quote_eur": ("EUR", "mean"),
    "room_eur": ("EUR", "sum"), "margin_eur": ("EUR", "sum"), "weight_kg": ("kg", "sum"),
    "price_per_kg_eur": ("EUR/kg", "mean"), "answer_seconds": ("s", "mean"), "ai_cost_usd": ("USD", "sum"),
}
NUMERIC = ["price_per_kg_eur", "weight_kg", "answer_seconds", "wants_fastest", "booked", "room_eur", "ai_cost_usd"]


def _n(x) -> float | None:
    try:
        return float(str(x).replace("EUR", "").strip()) if x not in (None, "") else None
    except ValueError:
        return None


def shipments() -> list[dict]:
    """One row per shipment with everything a chart can group by or measure."""
    booked = defaultdict(list)
    for b in economics.bookings():
        booked[b["deal"]].append(b)
    rows = []
    for r in store.records("deal", limit=100000):
        d, req = r["data"], r["data"].get("request") or {}
        q, bs = d.get("quote") or {}, booked.get(r["id"], [])
        at = d.get("received_at")
        when = datetime.fromisoformat(at).astimezone() if at else None
        quote, kg = _n(q.get("total") or q.get("amount")), _n(req.get("chargeable_kg") or req.get("weight_kg"))
        rows.append({
            "customer": (d.get("customer") or "unknown").split("@")[0].replace("-", " ").replace("_", " ").title(),
            "route": f"{req.get('origin')} to {req.get('destination')}" if req.get("origin") else "not priced",
            "origin": req.get("origin") or "not priced", "destination": req.get("destination") or "not priced",
            "airline": (bs[0]["airline"] if bs else (q.get("air") or {}).get("carrier")) or "none",
            "status": r["status"], "preference": d.get("preference") or "not said",
            "day": when.strftime("%a %d %b") if when else "unknown", "hour": when.strftime("%H:00") if when else "unknown",
            "_t": when.timestamp() if when else 0,
            "shipments": 1, "bookings": len(bs), "booked": 1 if bs else 0, "quoted_eur": quote,
            "booked_eur": float(sum(b["sell"] for b in bs)) if bs else None, "average_quote_eur": quote,
            "room_eur": float(sum(b["room"] for b in bs)) if bs else None,
            "margin_eur": float(sum(b["margin"] for b in bs)) if bs else None,
            "weight_kg": _n(req.get("weight_kg")), "price_per_kg_eur": quote / kg if quote and kg else None,
            "answer_seconds": _n(q.get("response_seconds")), "wants_fastest": 1 if d.get("preference") == "fastest" else 0 if d.get("preference") else None,
            "ai_cost_usd": store.usage(r["id"])["cost_usd"] or 0.0,
        })
    return rows


def _pick(rows: list[dict], status: str | None, text: str | None) -> list[dict]:
    words = (text or "").lower().split()
    return [x for x in rows if (not status or x["status"] == status)
            and all(w in " ".join(str(v) for v in x.values()).lower() for w in words)]


def _pearson(a: list, b: list) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 5:
        return None
    mx, my = sum(p[0] for p in pairs) / len(pairs), sum(p[1] for p in pairs) / len(pairs)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx, syy = sum((x - mx) ** 2 for x, _ in pairs), sum((y - my) ** 2 for _, y in pairs)
    return round(sxy / math.sqrt(sxx * syy), 3) if sxx and syy else None


def chart(measure: str, group_by: str | None = None, kind: str = "bar", status: str | None = None,
          text: str | None = None, title: str | None = None, limit: int | None = None) -> dict:
    """A chart as data: bars or a line of one measure by a group, or how the shipment figures move together."""
    rows = _pick(shipments(), status, text)
    spec = {"measure": measure, "group_by": group_by, "kind": kind, "status": status, "text": text,
            "title": title, "limit": limit}
    if kind == "matrix":
        cols = {v: [x[v] for x in rows] for v in NUMERIC}
        return {"spec": spec, "kind": "matrix", "title": title or "How the shipment figures move together",
                "vars": NUMERIC, "r": [[1.0 if i == j else _pearson(cols[a], cols[b]) for j, b in enumerate(NUMERIC)]
                                       for i, a in enumerate(NUMERIC)], "n": len(rows)}
    if measure not in MEASURES or group_by not in GROUPS:
        return {"error": f"measure is one of {sorted(MEASURES)}, group_by one of {GROUPS}"}
    unit, how = MEASURES[measure]
    groups: dict[str, list] = defaultdict(list)
    order: dict[str, float] = {}
    for x in rows:
        groups[x[group_by]].append(x)
        order[x[group_by]] = min(order.get(x[group_by], x["_t"]), x["_t"])
    points = []
    for label, xs in groups.items():
        if how == "count":
            v = float(len(xs))
        elif how == "rate":
            v = 100.0 * sum(x["booked"] for x in xs) / len(xs)
        else:
            vals = [x[measure] for x in xs if x[measure] is not None]
            if not vals:
                continue
            v = sum(vals) if how == "sum" else sum(vals) / len(vals)
        points.append({"label": label, "value": round(v, 2), "n": len(xs)})
    if kind == "line" or group_by in ("day", "hour"):
        points.sort(key=lambda p: order[p["label"]])
    else:
        points.sort(key=lambda p: -p["value"])
    if limit:
        points = points[:limit]
    total = round(sum(p["value"] for p in points), 2) if how in ("sum", "count") else None
    return {"spec": spec, "kind": "line" if kind == "line" else "bar", "unit": unit, "points": points, "total": total,
            "n": len(rows), "title": title or f"{measure.replace('_', ' ')} by {group_by}"}
