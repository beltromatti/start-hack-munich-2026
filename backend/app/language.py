"""Reading for the tools: carrier replies and tariff sheets, with a small model; units, in code.

The forwarder agent reads and writes to people itself. These are the data readers its tools use, so the agent
sees offers and lanes, not raw prose.
"""
from decimal import Decimal, InvalidOperation

from . import llm
from .config import settings
from .llm import strict

S, N, I, B = {"type": ["string", "null"]}, {"type": ["number", "null"]}, {"type": ["integer", "null"]}, {"type": "boolean"}

BID = strict({"offers": {"type": "array", "items": strict({
    "carrier": {"type": "string"}, "airline_code": S, "available": B, "total": N, "currency": S,
    "fx_eur_per_unit": N,
    "transit_days": N, "pickup_hours": N, "reference": S, "valid_until": S, "note": S})}})

TARIFF = strict({"airline": S, "currency": S, "valid_from": S, "valid_to": S, "notes": S,
                 "lanes": {"type": "array", "items": strict({
                     "origin": {"type": "string"}, "destination": {"type": "string"}, "transit_days": I,
                     "minimum": {"type": "string"}, "breaks_kg": {"type": "array", "items": {"type": "number"}},
                     "rates_per_kg": {"type": "array", "items": {"type": "string"}},
                     "fuel_per_kg": {"type": "string"}, "security_per_kg": {"type": "string"}})}})


def read_bid(sender: str, subject: str, body: str, run_id: str) -> list[dict]:
    out = llm.structured("bid", llm.prompt("bid"), f"From: {sender}\nSubject: {subject}\n\n{body}", BID,
                         model=settings.model_bid, run_id=run_id, agent="bids")
    return out["offers"]


def read_tariff(text: str, run_id: str, images: list[tuple[str, bytes]] | None = None) -> dict:
    return llm.structured("tariff", llm.prompt("tariff"), text, TARIFF, model=settings.model_tariff,
                          run_id=run_id, agent="tariff", images=images)


# ---- units (code, not the model) ---------------------------------------------------------------------------

def to_decimal(x) -> Decimal | None:
    try:
        return Decimal(str(x)) if x is not None and str(x).strip() != "" else None
    except InvalidOperation:
        return None


WEIGHT = {"kg": 1, "kgs": 1, "kilo": 1, "kilos": 1, "kilogram": 1, "kilograms": 1, "t": 1000, "ton": 1000,
          "tons": 1000, "tonne": 1000, "tonnes": 1000, "lb": Decimal("0.45359237"), "lbs": Decimal("0.45359237"),
          "pound": Decimal("0.45359237"), "pounds": Decimal("0.45359237"), "g": Decimal("0.001")}
VOLUME = {"cbm": 1, "m3": 1, "m³": 1, "cubicmeter": 1, "cubicmeters": 1, "cft": Decimal("0.0283168"),
          "ft3": Decimal("0.0283168"), "cuft": Decimal("0.0283168"), "l": Decimal("0.001"), "liter": Decimal("0.001"),
          "liters": Decimal("0.001"), "litre": Decimal("0.001")}
LENGTH = {"cm": Decimal("0.01"), "mm": Decimal("0.001"), "m": Decimal(1), "in": Decimal("0.0254"),
          "inch": Decimal("0.0254"), "inches": Decimal("0.0254"), "ft": Decimal("0.3048")}


def weight_kg(q: dict, pieces: int | None) -> Decimal | None:
    v = to_decimal((q or {}).get("value"))
    if v is None or v <= 0:
        return None
    v = v * Decimal(str(WEIGHT.get((q.get("unit") or "kg").lower().strip(), 1)))
    return v * pieces if q.get("per_piece") and pieces else v


def volume_cbm(q: dict, dims: list[dict], pieces: int | None) -> Decimal | None:
    v = to_decimal((q or {}).get("value"))
    if v is not None and v > 0:
        v = v * Decimal(str(VOLUME.get((q.get("unit") or "cbm").lower().replace(" ", ""), 1)))
        return v * pieces if q.get("per_piece") and pieces else v
    total = Decimal(0)
    for d in dims or []:
        l, w, h = (to_decimal(d.get(k)) for k in ("length", "width", "height"))
        if not (l and w and h):
            continue
        f = LENGTH.get((d.get("unit") or "cm").lower(), Decimal("0.01"))
        total += (l * f) * (w * f) * (h * f) * (d.get("count") or 1)
    return total or None
