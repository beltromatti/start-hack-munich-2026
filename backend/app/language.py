"""The language layer: what the model reads (customer mails, bids, tariffs) and writes (mails to customers).

The forms below are the flexibility layer: every option a carrier or customer can bring has a field, and
whatever does not fit lands in `flags` / `notes` instead of being forced into a wrong number.
"""
import re
from decimal import Decimal, InvalidOperation

from . import llm
from .config import settings
from .llm import strict

S, N, I, B = {"type": ["string", "null"]}, {"type": ["number", "null"]}, {"type": ["integer", "null"]}, {"type": "boolean"}


def enum(*values: str, null: bool = False) -> dict:
    return {"type": ["string", "null"] if null else "string", "enum": [*values, *([None] if null else [])]}


QUANTITY = strict({"value": N, "unit": S, "per_piece": B})

CUSTOMER = strict({
    "intent": enum("new_request", "accept", "decline", "info", "question", "other"),
    "customer_name": S, "company": S, "language": {"type": "string"},
    "origin_airport": S, "pickup_needed": B, "pickup_postcode": S, "pickup_city": S,
    "destination_airport": S, "destination_city": S,
    "pieces": I, "weight": QUANTITY, "volume": QUANTITY,
    "dimensions": {"type": "array", "items": strict({"count": I, "length": N, "width": N, "height": N, "unit": S})},
    "preference": enum("cheapest", "fastest", "unspecified"),
    "ready_date": S, "commodity": S,
    "flags": {"type": "array", "items": {"type": "string"}},
    "missing": {"type": "array", "items": {"type": "string"}},
    "references": {"type": "array", "items": {"type": "string"}},
    "notes": S,
})

BID = strict({"offers": {"type": "array", "items": strict({
    "carrier": {"type": "string"}, "airline_code": S, "available": B, "total": N, "currency": S,
    "transit_days": N, "pickup_hours": N, "reference": S, "valid_until": S, "note": S})}})

MAIL = strict({"body": {"type": "string"}})

TARIFF = strict({"airline": S, "currency": S, "valid_from": S, "valid_to": S, "notes": S,
                 "lanes": {"type": "array", "items": strict({
                     "origin": {"type": "string"}, "destination": {"type": "string"}, "transit_days": I,
                     "minimum": {"type": "string"}, "breaks_kg": {"type": "array", "items": {"type": "number"}},
                     "rates_per_kg": {"type": "array", "items": {"type": "string"}},
                     "fuel_per_kg": {"type": "string"}, "security_per_kg": {"type": "string"}})}})


def read_customer(thread_text: str, run_id: str) -> dict:
    return llm.structured("customer", llm.prompt("customer"), thread_text, CUSTOMER,
                          model=settings.model_parse, run_id=run_id, agent="rfq")


def read_bid(sender: str, subject: str, body: str, run_id: str) -> list[dict]:
    out = llm.structured("bid", llm.prompt("bid"), f"From: {sender}\nSubject: {subject}\n\n{body}", BID,
                         model=settings.model_bid, run_id=run_id, agent="bids")
    return out["offers"]


def read_tariff(text: str, run_id: str) -> dict:
    return llm.structured("tariff", llm.prompt("tariff"), text, TARIFF, model=settings.model_parse,
                          run_id=run_id, agent="tariff")


# ---- writing -----------------------------------------------------------------------------------------------

MONEY = re.compile(r"(?:€|\$|£|\b(?:EUR|USD|GBP|CHF)\b)\s*\d|\d[\d.,']*\s*(?:€|\$|£|\b(?:EUR|USD|GBP|CHF|euros?|dollars?)\b)",
                   re.IGNORECASE)


def write(kind: str, facts: dict, run_id: str, amount: str | None = None) -> str:
    """A mail body in the persona's voice. Checked in code: the amount appears exactly once and no other
    amount of money appears. If the model breaks that twice, a plain template is used instead."""
    system = llm.prompt("write").format(persona=settings.persona, company=settings.company)
    user = f"kind: {kind}\namount: {amount or 'none'}\nfacts: {facts}"
    for _ in range(2):
        try:
            body = llm.structured("write", system, user, MAIL, model=settings.model_write, run_id=run_id,
                                  agent="writer")["body"].strip()
        except RuntimeError:
            break
        if money_ok(body, amount):
            return body
    return template(kind, facts, amount)


def money_ok(body: str, amount: str | None) -> bool:
    found = MONEY.findall(body)
    if amount is None:
        return not found
    return body.count(amount) == 1 and len(found) == 1


def template(kind: str, facts: dict, amount: str | None) -> str:
    name = facts.get("customer_name")
    hi = f"Hi {name}," if name else "Hello,"
    sign = f"\n\nBest regards,\n{settings.persona}\n{settings.company}"
    if kind == "quote":
        route = facts.get("route", "")
        return (f"{hi}\n\nthanks for your request. For {route} our all-in price is {amount}, "
                f"flying with {facts.get('airline')} ({facts.get('transit_days')} days transit).\n\n"
                f"Just reply to this mail and we book it for you.{sign}")
    if kind == "question":
        return f"{hi}\n\nhappy to quote this. To price it right I still need: {', '.join(facts.get('missing', []))}.{sign}"
    if kind == "booked":
        return f"{hi}\n\nyour shipment is booked. Booking reference: {facts.get('booking_reference')}.{sign}"
    return f"{hi}\n\n{facts.get('text', 'thank you for your message.')}{sign}"


# ---- units (code, not the model) ---------------------------------------------------------------------------

def to_decimal(x) -> Decimal | None:
    try:
        return Decimal(str(x)) if x is not None else None
    except InvalidOperation:
        return None


def weight_kg(q: dict, pieces: int | None) -> Decimal | None:
    v = to_decimal(q.get("value"))
    if v is None or v <= 0:
        return None
    unit = (q.get("unit") or "kg").lower()
    f = {"kg": 1, "kgs": 1, "kilo": 1, "kilos": 1, "t": 1000, "ton": 1000, "tons": 1000, "tonnes": 1000,
         "lb": Decimal("0.45359237"), "lbs": Decimal("0.45359237"), "g": Decimal("0.001")}.get(unit, 1)
    v = v * Decimal(str(f))
    if q.get("per_piece") and pieces:
        v *= pieces
    return v


def volume_cbm(q: dict, dims: list[dict], pieces: int | None) -> Decimal | None:
    v = to_decimal(q.get("value"))
    if v is not None and v > 0:
        unit = (q.get("unit") or "cbm").lower().replace(" ", "")
        f = {"cbm": 1, "m3": 1, "m³": 1, "cubicmeters": 1, "cft": Decimal("0.0283168"), "ft3": Decimal("0.0283168"),
             "l": Decimal("0.001"), "liters": Decimal("0.001")}.get(unit, 1)
        v = v * Decimal(str(f))
        return v * pieces if q.get("per_piece") and pieces else v
    total = Decimal(0)
    for d in dims or []:
        l, w, h = (to_decimal(d.get(k)) for k in ("length", "width", "height"))
        if not (l and w and h):
            continue
        f = {"cm": Decimal("0.01"), "mm": Decimal("0.001"), "m": Decimal(1), "in": Decimal("0.0254")}.get(
            (d.get("unit") or "cm").lower(), Decimal("0.01"))
        total += (l * f) * (w * f) * (h * f) * (d.get("count") or 1)
    return total or None
