"""Reading for the tools: carrier replies and tariff sheets, with a small model; units, in code.

The forwarder agent reads and writes to people itself. These are the data readers its tools use, so the agent
sees offers and lanes, not raw prose.
"""
import re
from decimal import Decimal, InvalidOperation

from . import llm
from .config import settings
from .llm import strict

S, N, I, B = {"type": ["string", "null"]}, {"type": ["number", "null"]}, {"type": ["integer", "null"]}, {"type": "boolean"}

BID = strict({"offers": {"type": "array", "items": strict({
    "carrier": {"type": "string"}, "airline_code": S, "available": B, "total": N, "currency": S,
    "fx_eur_per_unit": N,
    # when there is no total, the parts it is made of (code computes the total for the weight we asked)
    "rate_per_kg": N, "minimum_charge": N, "surcharges_per_kg": N, "fixed_fees": N, "billed_kg": N,
    # how long it takes, as written: "8 hours" -> 8, "hours"; "4 days" -> 4, "days" (code converts)
    "time_value": N, "time_unit": S,
    "reference": S, "valid_until": S, "note": S})}})

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


def unit(u: str | None) -> str:
    """A unit as written, in the form the tables use: 'KGS.', 'cu. ft', 'm³', 'Metric Tons' -> 'kgs', 'cuft', 'm3',
    'metrictons'."""
    return re.sub(r"[\s.^]", "", (u or "").lower()).replace("³", "3")


_LB, _CFT = Decimal("0.45359237"), Decimal("0.0283168")
WEIGHT = {**dict.fromkeys(("kg", "kgs", "kilo", "kilos", "kilogram", "kilograms", "kilogramme", "kilogrammes"), 1),
          **dict.fromkeys(("t", "ton", "tons", "tonne", "tonnes", "mt", "metricton", "metrictons"), 1000),
          **dict.fromkeys(("lb", "lbs", "pound", "pounds"), _LB),
          **dict.fromkeys(("g", "gram", "grams", "gramme", "grammes"), Decimal("0.001"))}
VOLUME = {**dict.fromkeys(("cbm", "m3", "cum", "cubicmeter", "cubicmeters", "cubicmetre", "cubicmetres"), 1),
          **dict.fromkeys(("cft", "ft3", "cuft", "cubicfoot", "cubicfeet"), _CFT),
          **dict.fromkeys(("l", "ltr", "liter", "liters", "litre", "litres"), Decimal("0.001")),
          **dict.fromkeys(("in3", "cuin", "cubicinch", "cubicinches"), Decimal("0.000016387064"))}
LENGTH = {**dict.fromkeys(("cm", "cms", "centimeter", "centimeters", "centimetre", "centimetres"), Decimal("0.01")),
          **dict.fromkeys(("mm", "millimeter", "millimeters", "millimetre", "millimetres"), Decimal("0.001")),
          **dict.fromkeys(("m", "meter", "meters", "metre", "metres"), Decimal(1)),
          **dict.fromkeys(("in", "inch", "inches", '"'), Decimal("0.0254")),
          **dict.fromkeys(("ft", "foot", "feet", "'"), Decimal("0.3048"))}


def unknown_units(lots: list[dict]) -> list[str]:
    """Units in the shipment our tables do not know. They are never guessed: a 'metric tons' read as kg, or
    'cubic feet' as cbm, is a price wrong by a factor of 1000 or 35."""
    out = []
    for lot in lots or []:
        for key, table, default in (("weight", WEIGHT, "kg"), ("volume", VOLUME, "cbm")):
            u = ((lot.get(key) or {}).get("unit") or default)
            if (lot.get(key) or {}).get("value") is not None and unit(u) not in table:
                out.append(f"{key} unit '{u}'")
        d = lot.get("dimensions") or {}
        if d and unit(d.get("unit") or "cm") not in LENGTH:
            out.append(f"dimension unit '{d.get('unit')}'")
    return out


def weight_kg(q: dict, pieces: int | None) -> Decimal | None:
    v = to_decimal((q or {}).get("value"))
    f = WEIGHT.get(unit((q or {}).get("unit") or "kg"))
    if v is None or v <= 0 or f is None:
        return None
    v = v * Decimal(str(f))
    return v * pieces if q.get("per_piece") and pieces else v


def volume_cbm(q: dict, dims: list[dict], pieces: int | None) -> Decimal | None:
    v = to_decimal((q or {}).get("value"))
    f = VOLUME.get(unit((q or {}).get("unit") or "cbm"))
    if v is not None and v > 0 and f is not None:
        v = v * Decimal(str(f))
        return v * pieces if q.get("per_piece") and pieces else v
    total = Decimal(0)
    for d in dims or []:
        l, w, h = (to_decimal(d.get(k)) for k in ("length", "width", "height"))
        f = LENGTH.get(unit(d.get("unit") or "cm"))
        if not (l and w and h) or f is None:
            continue
        total += (l * f) * (w * f) * (h * f) * (d.get("count") or 1)
    return total or None


UNITS_PER_DAY = {"h": Decimal(24), "hr": Decimal(24), "hrs": Decimal(24), "hour": Decimal(24), "hours": Decimal(24),
                 "stunde": Decimal(24), "stunden": Decimal(24), "min": Decimal(1440), "minutes": Decimal(1440),
                 "d": Decimal(1), "day": Decimal(1), "days": Decimal(1), "tag": Decimal(1), "tage": Decimal(1),
                 "week": Decimal("0.142857"), "weeks": Decimal("0.142857")}


def days(value, unit) -> Decimal | None:
    """A duration as written (8, "hours") in days, by code: the model never converts units. The unit is its first
    word ("hours from order to collection" is hours); a unit we do not know is None, never taken as days (round 67's
    reader gave 28 with that unit: 28 days of pickup)."""
    v = to_decimal(value)
    if v is None:
        return None
    words = re.findall(r"[a-zäöü]+", (unit or "days").lower()) or ["days"]
    per_day = next((UNITS_PER_DAY[w] for w in words if w in UNITS_PER_DAY), None)  # "business days" is days
    return None if per_day is None else (v / per_day).quantize(Decimal("0.001"))


_TIME = (r"(?:lead|pickup|pick-up|collection|transit)\s*time\s*[:\-]?\s*(?:is\s*)?(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|days?)\b",
         r"(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|days?)\s*(?:from|after)\s*(?:your\s*|the\s*)?order",
         r"(?:collection|pickup|collect(?:ed)?)\s*in\s*(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|days?)\b")


_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                       "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_WORDS.update({"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70})


def _digits(text: str) -> str:
    """Small numbers said in words as digits ('seven hours', 'twenty-four hours'), for reading times."""
    def one(m: re.Match) -> str:
        parts = re.split(r"[-\s]+", m.group(0).lower())
        return str(sum(_WORDS[x] for x in parts))
    names = "|".join(sorted(_WORDS, key=len, reverse=True))
    return re.sub(rf"\b(?:{names})(?:[-\s]+(?:{names}))?\b(?=\s+(?:hours?|hrs?|days?)\b)", one, text or "", flags=re.I)


EN = set("the and please could you your our is are for with we to of a an this that would be will".split())
DE = set("der die das und bitte wir ist sind für mit sie ihr ihre zu von ein eine den dem uns unser können".split())
# Other languages' small words, so that a French, Italian, Spanish, Dutch or Turkish mail full of English trade terms
# ("all in rate", "pick-up", "for 300 kg") is not counted as English: the trade writes its jargon in English.
OTHER = set("le la les des et pour nous vous est une du avec merci bonjour il lo gli per che sono della grazie "
            "buongiorno el los las para por gracias hola nuestro het een voor wij ons graag bedankt ve bir için bu "
            "ile lütfen merhaba teşekkürler rica ederim olarak".split())
# Where the quoted older mail starts in a reply or a forward: their own words are what stands above it.
_QUOTE = re.compile(r"^\s*(>|-{2,}\s*(original|forwarded|ursprüngliche|weitergeleitete)|on .{3,80} wrote:|"
                    r"am .{3,80} schrieb|(from|von|de|da|kimden):\s)", re.I | re.M)


def own_words(text: str) -> str:
    """The newest text of a mail, without the quoted mail or forward under it (all of it when nothing is above)."""
    m = _QUOTE.search(text or "")
    return (text[:m.start()] if m and text[:m.start()].strip() else text) or ""


def language_of(text: str) -> str | None:
    """The language a mail's own words are in, when it is clear (English or German), counted by code: a German
    company writing in English writes English (rounds 29, 49, 69 were answered in German). None when unclear: a
    third language in the words, or English trade terms in a German or foreign sentence, is the model's to read."""
    words = re.findall(r"[^\W\d_]+", own_words(text).lower())
    en, de, other = (sum(w in s for w in words) for s in (EN, DE, OTHER))
    if other >= 2:
        return None
    if en >= 4 and en >= 3 * de:
        return "English"
    if de >= 4 and de >= 3 * en:
        return "German"
    return None


def time_in(text: str) -> Decimal | None:
    """A trucker's time as its mail states it, by code, when the reader missed it (round 63: three of three
    attachment offers came back without a time, and a slow trucker looked instant in the 50/50 pick)."""
    text = _digits(text or "")
    for pattern in _TIME:
        m = re.search(pattern, text, re.I)
        if m:
            return days(m.group(1).replace(",", "."), m.group(2))
    return None
