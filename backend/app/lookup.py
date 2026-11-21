"""Finding a deal from what a customer says about it (the crm tool).

The model translates the question into fields (IATA codes, kg, ISO dates, references); this module compares them
with each deal's record, with the tolerances a person would use: a weight within 5 %, a ready date within a day (an
exact fit scores higher), a reference only as a whole word (SM-12 is not SM-123). Each candidate says which fields fit and which differ, so the
agent can tell two shipments of the same customer apart instead of taking the newest.
Measured Sat 21 Nov: the old substring count found 0 of 19 real tracking cases at 98 deals when the question gave
the weight in tonnes or the date as "25 Nov" (probe in jan-crm-search/PLAN.md).
"""
import difflib
import json
import math
import re
import time
from datetime import date

from . import store

GENERIC = {"gmbh", "kg", "ag", "co", "ltd", "inc", "se", "the", "and", "und", "hackloop", "mail"}
ALL = 1_000_000  # the register's default page is 500 deals: a search must see the whole night
FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "á": "a", "ó": "o"})


def tokens(text: str, parts: bool = True) -> set[str]:
    """Whole words. A hyphenated word (BK-3ZY8SE7F, lindqvist-medtech) stays one word and, with parts, also gives
    its pieces, so a record found by "3ZY8SE7F" still is; a question's SM-12 is compared whole and never hits SM-123."""
    out = set()
    for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", (text or "").lower().translate(FOLD)):
        out.add(t)
        if parts:
            out.update(t.split("-"))
    return out


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _day(x) -> date | None:
    try:
        return date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None


def _near(word: str, vocab: set[str]) -> bool:
    """A company name with a typo or another spelling (Electronic / Elektronik) still counts."""
    return word in vocab or (len(word) >= 5 and bool(difflib.get_close_matches(word, [v for v in vocab if len(v) >= 5],
                                                                                n=1, cutoff=0.8)))


def find(reference=None, customer=None, origin=None, destination=None, weight_kg=None, ready_date=None,
         text=None) -> list[dict]:
    """Every deal with at least one fitting field, best first: {rec, booking, score, matched, differs}."""
    deals = store.records("deal", limit=ALL)
    rows = []
    for rec in deals:
        d = rec["data"]
        b = store.get(f"booking-{d.get('root')}")
        bd = (b or {}).get("data") or d.get("booking") or {}
        req = d.get("request") or {}
        said = " ".join(m["body"] or "" for m in store.thread(d["root"]) if m["direction"] == "in") \
            if d.get("root") is not None else ""
        refs = tokens(" ".join(str(x) for x in (rec["id"], bd.get("booking_reference"), bd.get("team_reference"),
                                                 bd.get("rate_id")) if x))
        who = tokens(f"{d.get('customer') or ''} {said}")
        rows.append((rec, b, bd, req, refs, who, tokens(json.dumps({"deal": d, "booking": bd}, default=str) + said)))

    df: dict[str, int] = {}
    for *_, hay in rows:
        for t in hay:
            df[t] = df.get(t, 0) + 1
    n = max(1, len(rows))
    out = []
    for rec, b, bd, req, refs, who, hay in rows:
        score, matched, differs = 0.0, [], []

        def field(name, given, fits, weight):
            nonlocal score
            if given in (None, "", []):
                return
            if fits:
                score += weight
                matched.append(name)
            else:
                differs.append(name)

        if reference:
            field("reference", reference, any(t in refs for t in tokens(reference, parts=False) if re.search(r"\d", t)), 10)
        if customer:
            words = [w for w in tokens(customer) if w not in GENERIC and len(w) > 2 and "-" not in w]
            field("customer", customer, bool(words) and sum(_near(w, who) for w in words) >= max(1, len(words) / 2), 3)
        if origin:
            o = origin.strip().upper()
            field("origin", origin, o in {str(req.get("origin") or "").upper(), str(req.get("pickup_postcode") or "")}, 2)
        if destination:
            field("destination", destination, destination.strip().upper() == str(req.get("destination") or "").upper(), 2)
        w, have = _num(weight_kg), _num(req.get("weight_kg") or bd.get("weight_kg"))
        if w:
            off = abs(w - have) / have if have else 1
            field("weight" if off <= 0.01 else "weight (within 5 %)", weight_kg, off <= 0.05, 2 if off <= 0.01 else 1)
        r, ready = _day(ready_date), _day(req.get("ready_date") or bd.get("ready_date"))
        if r:
            off = abs((r - ready).days) if ready else 9
            field("ready_date" if off == 0 else "ready_date (1 day off)", ready_date, off <= 1, 2 if off == 0 else 1)
        if text:
            score += sum(math.log(1 + n / df[t]) / 4 for t in tokens(text) - GENERIC if t in hay)
        given = any(x not in (None, "") for x in (reference, customer, origin, destination, weight_kg, ready_date, text))
        if score or not given:
            out.append({"rec": rec, "booking": b, "score": round(score, 2), "matched": matched, "differs": differs})
    out.sort(key=lambda x: (-x["score"], -x["rec"]["updated_at"]))
    return out


def history(customer: str | None, exclude: str | None = None, n: int = 3) -> list[str]:
    """What we booked for this sender before, newest first, one short line each, so the agent can remember them for
    about 60 tokens instead of a search: "Sat 21 Nov 2026 CGN-SGN (Ho Chi Minh City) 410 kg, booked Meridian, not
    flown yet, arrives Tue 24 Nov 2026". Only booked work: a request we lost is nothing to remind them of. Each line
    says where the shipment stands, from the dates tracking uses, so the agent can only say what is true (offline
    test, Sat 21 Nov: "hope it arrived well" came out for shipments that had not been collected)."""
    from . import kit
    from .tools import _ts, timeline  # the dates the quote and the tracking answer use (tools imports this module)
    if not customer:
        return []
    who = customer.strip().lower()
    out = []
    for rec in store.records("deal", limit=ALL):
        d = rec["data"]
        if rec["id"] == exclude or (d.get("customer") or "").strip().lower() != who:
            continue
        req, bd = d.get("request") or {}, d.get("booking") or {}
        if not req.get("destination") or not bd or bd.get("status") == "failed":
            continue
        when = time.strftime("%a %d %b %Y", time.gmtime((_ts(d.get("received_at")) if d.get("received_at") else 0)
                                                     or rec["updated_at"]))
        kg = f" {req['weight_kg']} kg" if req.get("weight_kg") else ""
        place = kit.DESTINATIONS.get(req["destination"], "").split(" / ")[0]
        what = f"booked {bd.get('airline') or ''}".strip()
        t = timeline(bd)
        stage = t.get("expected_stage_now")
        if stage == "arrived":
            what += f", arrived {t['estimated_arrival']}"
        elif t:
            what += f", {'in the air' if stage == 'in transit' else 'not flown yet'}, arrives {t['estimated_arrival']}"
        out.append(f"{when} {req.get('origin') or '?'}-{req['destination']}{f' ({place})' if place else ''}{kg}, {what}")
        if len(out) == n:
            break
    return out
