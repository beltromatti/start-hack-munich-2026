"""The desk's economics, computed from the register in one place: what we sold, what the carriers charge, what we
keep, and what the AI costs us. The Efficiency page and the desk's assistant read the same numbers.

Per booking: the customer pays the booking's all-in total; the carriers charge their legs (the airline's booked
price, which can differ from its quote, and the trucker); insurance and the customer's own charges are passed on.
What is left is our margin. Giulia quotes carrier prices as they are (forwarder.md: margins are not part of the
quote, as the challenge scores the best price), so it is zero today, computed and not assumed. The room to the
next option is what a margin could be while every booked quote stays below the customer's next priced option.

For the demo after the challenge, one value in the register (kv `margin_demo_percent`) sets the margin as a share of
each booking's price; the carriers' part is then what is left, so every total still adds up. It is the one figure
on the desk that is not from the record, and `margin_demo` says so in the API.
"""
from decimal import Decimal

from . import store
from .pricing import money


def _d(x) -> Decimal:
    try:
        return Decimal(str(x).replace("EUR", "").strip()) if x not in (None, "") else Decimal(0)
    except Exception:
        return Decimal(0)


def demo_percent() -> Decimal | None:
    v = store.kv_get("margin_demo_percent")
    return Decimal(v) if v not in (None, "") else None


def bookings() -> list[dict]:
    """Every booking that stands, with what the customer pays and what goes where."""
    demo = demo_percent()
    out = []
    for r in store.records("deal", limit=100000):
        d = r["data"]
        if r["status"] == "cancelled":
            continue
        options = d.get("options") or {}
        for b in d.get("bookings") or ([d["booking"]] if d.get("booking") else []):
            if (b.get("status") or "").lower() in ("cancelled", "canceled"):
                continue
            opt = options.get(b.get("option") or "") or {}
            sell = _d(b.get("amount"))
            main = d.get("booking") or {}
            changed = b.get("price_changed") or (main.get("price_changed") if main.get("option") == b.get("option") else None)
            delta = _d(changed["booked"]) - _d(changed["quoted"]) if changed else Decimal(0)
            air = _d((opt.get("air") or {}).get("total")) + delta
            pickup = _d((b.get("pickup") or opt.get("pickup") or {}).get("total"))
            passed = _d(opt.get("insurance")) + _d(opt.get("extra_charges"))
            prefix = (b.get("option") or "A")[0]
            dearer = sorted(_d(o.get("total")) for k, o in options.items()
                            if k[:1] == prefix and _d(o.get("total")) > _d(opt.get("total")))
            margin = sell - air - pickup - passed
            if demo is not None:  # the demo margin: a share of the price, the carriers' part what is left
                margin = money(sell * demo / 100)
                air, pickup = sell - passed - margin, Decimal(0)
            out.append({"deal": r["id"], "customer": d.get("customer"), "airline": b.get("airline"),
                        "route": b.get("route"), "sell": sell, "carriers": air + pickup, "passed_on": passed,
                        "margin": margin,
                        "room": (dearer[0] - _d(opt.get("total"))) if dearer else Decimal(0)})
    return out


def economics() -> dict:
    deals = store.records("deal", limit=100000)
    bs = bookings()
    revenue = sum((b["sell"] for b in bs), Decimal(0))
    carriers = sum((b["carriers"] for b in bs), Decimal(0))
    passed = sum((b["passed_on"] for b in bs), Decimal(0))
    margin = sum((b["margin"] for b in bs), Decimal(0))
    room = sum((b["room"] for b in bs), Decimal(0))
    ai = sum(store.usage(r["id"])["cost_usd"] or 0 for r in deals)
    pct = lambda x: f"{(x / revenue * 100).quantize(Decimal('0.01'))}" if revenue else None  # noqa: E731
    n = len(bs)
    return {
        "requests": len(deals), "quoted": sum(1 for r in deals if (r["data"].get("quote") or {}).get("amount")),
        "bookings": n, "revenue_eur": str(money(revenue)), "carrier_cost_eur": str(money(carriers)),
        "passed_on_eur": str(money(passed)), "margin_eur": str(money(margin)), "margin_percent": pct(margin),
        "room_eur": str(money(room)), "room_percent": pct(room),
        "room_bookings": sum(1 for b in bs if b["room"] > 0),
        "revenue_per_booking_eur": str(money(revenue / n)) if n else None,
        "ai_cost_usd": round(ai, 4), "ai_cost_per_request_usd": round(ai / len(deals), 5) if deals else None,
        "ai_cost_per_booking_usd": round(ai / n, 5) if n else None,
        "margin_demo": demo_percent() is not None,
    }
