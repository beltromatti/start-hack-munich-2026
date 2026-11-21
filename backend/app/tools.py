"""The forwarder's tools: few, distinct, powerful. Each is thin over the engine (forwarder.py) and the register.

What a tool guarantees, the model never has to: prices and totals are computed here, mails go only where 5U allows
and land in the right thread, the first quote of a thread is recorded as the quote, bookings use real references.
What to do, when, and how to say it is the model's.
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from . import lookup, kit, pricing, store
from .config import settings
from .kit import RATEDESK, TRACKING

S, N, I = {"type": ["string", "null"]}, {"type": ["number", "null"]}, {"type": ["integer", "null"]}
DONE = {"type": "boolean", "description": "true when this finishes what the mail needs: the turn closes here, "
        "without another model call (each one costs). false when you still want to do something after it."}


def obj(props: dict, desc: str | None = None) -> dict:
    o = {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}
    if desc:
        o["description"] = desc
    return o


def nullable(o: dict) -> dict:
    return {"anyOf": [o, {"type": "null"}]}


QUANTITY = obj({"value": N, "unit": S, "per_piece": {"type": "boolean"}})
SHIPMENT = obj({
    "origin_airport": {**S, "description": "IATA code of the German departure airport, if the customer names one"},
    "pickup": nullable(obj({"postcode": S, "city": S},
                           "door-to-port, only when the customer asks us to collect the goods (pickup, trucking, "
                           "from our site, ab Werk): where the truck collects them. An address in a signature or "
                           "letterhead is not a pickup request: null")),
    "destination_airport": {**S, "description": "IATA code of the destination airport. A city is its airport in "
                                                "our network: " + ", ".join(
                                                    f"{c} {n}" for c, n in kit.DESTINATIONS.items())},
    "lots": {"type": "array", "description": (
        "the goods as the customer lists them, one entry per group of pieces (a simple shipment is one lot). "
        "Copy numbers and units as written; our code adds the lots up and converts units"),
        "items": obj({
            "pieces": I,
            "weight": {**QUANTITY, "description": "gross weight as written (never net): value, unit (kg, lb, t), "
                                                  "per_piece true if it is the weight of one piece"},
            "volume": {**QUANTITY, "description": "as written: value, unit (cbm, cft, l), per piece or for the lot; "
                                                  "null values if not given"},
            "dimensions": nullable(obj({"length": N, "width": N, "height": N, "unit": S},
                                       "size of ONE piece of this lot, as written")),
        })},
    "cargo": obj({"commodity": S, "ready_date": S, "notes": S}),
})


def fn(name: str, desc: str, props: dict) -> dict:
    """A tool in the Responses API shape, strict: the model's arguments always match the schema."""
    return {"type": "function", "name": name, "description": desc, "strict": True, "parameters": obj(props)}


TOOLS = [
    fn("get_offers",
       "Price a shipment: asks every airline and trucker that can carry it (by mail, in parallel), reads the rate "
       "portal and our rate sheets, waits for the answers and returns the priced options, all-in totals computed by "
       "code (chargeable weight, cheaper weight breaks, minimums, surcharges, pickup leg), with the option that fits "
       "each preference. Pass the shipment as the customer described it, units as written. With shipment null it "
       "only waits for the replies still missing and returns the options again (or, when there is nothing to "
       "price, what the carriers answered). Carriers answer in 15-60 s (live, "
       "Sat 21 Nov); waiting up to about 90 s still gets the quote out within the 2 minutes that score best. "
       "wait_seconds is how long to wait at most: it returns as soon as everyone answered.",
       {"shipment": nullable(SHIPMENT),
        "preference": {"type": "string", "enum": ["cheapest", "fastest", "unspecified"]},
        "wait_seconds": {"type": "number"}}),
    fn("send_mail",
       "Send a mail. By default it answers the person who wrote the mail you are handling, in this thread. "
       "kind says what it is; for a quote give option_id, so the CRM records exactly that option and total "
       "(5U scores only the first quote of a thread). `to` only to write to someone else in this thread's deal.",
       {"kind": {"type": "string", "enum": ["quote", "question", "reply", "booking_confirmation", "tracking_answer",
                                            "decline", "other"]},
        "body": {"type": "string", "description": "the whole mail body, plain text"},
        "option_id": S, "to": S, "done": DONE}),
    fn("book",
       "Book an option of this deal with the carrier: by its rate reference on the portal (a fresh rate if it "
       "expired), otherwise by mail to the airline. Returns the booking with its reference and status.",
       {"option_id": {"type": "string"}}),
    fn("crm",
       "Search our CRM for a deal or booking. Customers rarely give a reference: put what they wrote into the fields "
       "in our form (airport codes for cities, kg for tonnes or pounds, YYYY-MM-DD for any date), null for what they "
       "did not say, and the rest of their words in query. Each match says which fields fit and which differ, so two "
       "shipments of one customer can be told apart. All null and empty query: the latest deals.",
       {"query": {**S, "description": "any other words: company, goods, airline, a phrase from their mail"},
        "reference": {"type": ["string", "null"], "description": "BK-..., SM-..., R-..., deal-... if they gave one"},
        "customer": {"type": ["string", "null"], "description": "company or sender address"},
        "origin": {"type": ["string", "null"], "description": "IATA of the German airport, or the pickup postcode"},
        "destination": {"type": ["string", "null"], "description": "IATA of the destination airport"},
        "weight_kg": {"type": ["number", "null"], "description": "actual weight in kg"},
        "ready_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"}}),
    fn("deal",
       "The whole record of a deal: the thread, the shipment, every offer and carrier message, the options, the "
       "quote, the booking, notes. No id: the deal of this thread.",
       {"deal_id": S}),
    fn("mail_carrier",
       "Write to a carrier or trucker from our carrier list, or to the rate desk: to answer a question they asked, "
       "to ask for something, to book by mail. Their answer comes back into this deal (get_offers with shipment "
       "null waits for it). in_reply_to: the id of their mail you answer, if any.",
       {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "in_reply_to": I}),
    fn("carrier_status",
       "Ask the airline of a booked shipment where it is now: there is no status API, the airline answers by mail "
       "(a position, a delay, a disruption, an arrival time). The question goes in the airline's thread with our "
       "references; it waits for the answer (they reply in 15-60 s), keeps it on the booking as the latest status "
       "and returns it with the booking's facts. deal_id: the shipment's deal (from crm). question: your own wording, "
       "or null for a standard status request.",
       {"deal_id": {"type": "string"}, "question": S, "wait_seconds": {"type": "number"}}),
    fn("note",
       "Write a note on the deal for the team (what you noticed, what you decided and why). flag: yellow when a "
       "person should look at it, red when something is wrong or risky; none otherwise.",
       {"text": {"type": "string"}, "flag": {"type": "string", "enum": ["none", "yellow", "red"]}}),
    fn("no_reply",
       "Nothing needs to be sent for the mail you are handling (for example a thank-you after the booking). Say why.",
       {"reason": {"type": "string"}, "done": DONE}),
]


@dataclass
class Ctx:
    fw: Any
    session_id: str
    deal_id: str
    root: int
    task: str
    mail: dict | None                     # the mail this execution handles (None: a person wrote in the session)
    outcome: list[str] = field(default_factory=list)
    done: bool = False  # the model said this turn finishes the mail: no further call


def run(ctx: Ctx, name: str, args: dict) -> dict:
    f = {"get_offers": get_offers, "send_mail": send_mail, "book": book, "crm": crm, "deal": deal,
         "mail_carrier": mail_carrier, "carrier_status": carrier_status, "note": note,
         "no_reply": no_reply}.get(name)
    if f is None:
        return {"error": f"unknown tool {name}"}
    return f(ctx, **args)


# ---- implementations ---------------------------------------------------------------------------------------

def get_offers(ctx: Ctx, shipment: dict | None, preference: str, wait_seconds: float) -> dict:
    _ensure_deal(ctx)
    store.update(ctx.deal_id, lambda r: ("pricing" if r["status"] == "new" and shipment is not None else r["status"],
                                         {**r["data"], "preference": preference}))
    out = ctx.fw.collect_offers(ctx.deal_id, shipment, preference, wait_seconds)
    before = lookup.history((store.get(ctx.deal_id) or {}).get("data", {}).get("customer"), exclude=ctx.deal_id)
    if before:
        out["this_customer_before"] = before
    if out.get("missing"):
        store.update(ctx.deal_id, lambda r: ("waiting_customer", r["data"]))
    return out


def send_mail(ctx: Ctx, kind: str, body: str, option_id: str | None, to: str | None, done: bool = False) -> dict:
    ctx.done = ctx.done or bool(done)
    m = ctx.mail or _last_inbound(ctx.root)
    if m is None:
        return {"error": "no mail in this thread to answer"}
    to = (to or m["sender"]).strip().lower()
    allowed = {x["sender"].lower() for x in store.thread(ctx.root) if x["direction"] == "in"} | {TRACKING, RATEDESK}
    if to not in allowed and not kit.world().carrier_by_email(to):
        return {"error": f"{to} is not part of this thread; 5U only delivers to customers who wrote to us, "
                         f"carriers on our list, the rate desk and the tracking desk"}
    parent = next((x for x in reversed(store.thread(ctx.root)) if x["direction"] == "in" and x["sender"].lower() == to),
                  m)
    subject = parent["subject"] or "Your shipment"
    subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    sent = ctx.fw.api.send(to, subject, body, in_reply_to=parent["id"])
    store.save_mail(sent, "out", kind, handled=True)
    ctx.outcome.append(kind)
    store.log("forwarder", "mail_out", f"{kind} to {to}: {body[:140]}", {"mail": sent["id"], "body": body,
                                                                           "option": option_id}, run_id=ctx.deal_id)
    result: dict[str, Any] = {"sent": sent["id"], "to": to}
    if kind == "question" and store.get(ctx.deal_id):
        store.update(ctx.deal_id, lambda r: ("waiting_customer" if r["status"] in ("new", "pricing") else r["status"],
                                             r["data"]))
    if kind == "quote":
        result.update(_record_quote(ctx, option_id, body, sent))
    return result


MONEY = re.compile(r"(?:€|\$|£|\b(?:EUR|USD|GBP|CHF)\b)\s*\d[\d.,']*|\d[\d.,']*\s*(?:€|\$|£|\b(?:EUR|USD|GBP|CHF|euros?|dollars?)\b)",
                   re.IGNORECASE)


def _quote_amounts(ctx: Ctx, option_id: str | None, body: str) -> str | None:
    """None when the quote carries exactly one amount of money, the option's total. Else what to change."""
    d = store.get(ctx.deal_id)["data"] if store.get(ctx.deal_id) else {}
    opt = (d.get("options") or {}).get(option_id or "")
    if not opt:
        return None  # no option to check against (recorded as such by _record_quote)
    found = MONEY.findall(body)
    if body.count(opt["total_text"]) == 1 and len(found) == 1:
        return None
    return (f"not sent: a quote carries exactly one amount of money, the total of option {option_id} written as "
            f"{opt['total_text']}, once. This text has {len(found)}: {found[:4]}. One mail, one option, one total; "
            f"another option can be named in words (airline, days) without its price")


def _record_quote(ctx: Ctx, option_id: str | None, body: str, sent: dict) -> dict:
    d = store.get(ctx.deal_id)["data"] if store.get(ctx.deal_id) else {}
    opt = (d.get("options") or {}).get(option_id or "")
    if not opt:
        store.log("forwarder", "info", f"quote sent without a known option ({option_id})", run_id=ctx.deal_id)
        return {"note": "no option recorded with this quote (option_id unknown): the CRM has no price for it"}
    wrong = _quote_amounts(ctx, option_id, body)  # diagnostics, not a gate: we measure, the prompt teaches
    if wrong:
        store.log("forwarder", "error", f"quote mail amounts: {wrong}"[:400], run_id=ctx.deal_id)
    first = not d.get("quote")
    took = time.time() - _ts(d.get("received_at"))
    q = {"option": option_id, "amount": opt["total_text"], "total": opt["total"], "air": opt["air"],
         "pickup": opt["pickup"], "mail": sent["id"], "at": time.time(), "response_seconds": round(took, 1)}
    store.update(ctx.deal_id, lambda r: ("quoted" if r["status"] in ("new", "pricing", "waiting_customer") else r["status"], {
        **r["data"], "quote": r["data"].get("quote") or q, "quotes": r["data"].get("quotes", []) + [q]}))
    store.log("forwarder", "decision", f"quoted {opt['total_text']} ({opt['air']['carrier']}) in {took:.0f}s",
              q, run_id=ctx.deal_id)
    return {"recorded_quote": opt["total_text"], "first_quote_in_thread": first}


def book(ctx: Ctx, option_id: str) -> dict:
    _ensure_deal(ctx)
    return ctx.fw.book_option(ctx.deal_id, option_id)


def crm(ctx: Ctx, query: str = "", reference: str | None = None, customer: str | None = None,
        origin: str | None = None, destination: str | None = None, weight_kg: float | None = None,
        ready_date: str | None = None) -> dict:
    found = lookup.find(reference=reference, customer=customer, origin=origin, destination=destination,
                        weight_kg=weight_kg, ready_date=ready_date, text=query)
    out = {"matches": [{**_summary(x["rec"], x["booking"]), "matched": x["matched"], "differs": x["differs"]}
                       for x in found[:10]], "total_matches": len(found)}
    tied = [x for x in found if x["score"] == found[0]["score"]] if found and found[0]["score"] else []
    if len(tied) > 1:
        out["note"] = f"{len(tied)} deals fit equally well: compare them, or ask the customer for what tells them apart"
    return out


def deal(ctx: Ctx, deal_id: str | None) -> dict:
    rec = store.get(deal_id or ctx.deal_id)
    if not rec:
        return {"error": "no such deal"}
    d = rec["data"]
    thread = [{"id": m["id"], "from": m["sender"], "to": m["recipient"], "at": m["received_at"],
               "subject": m["subject"], "body": m["body"]} for m in store.thread(d["root"])]
    return {"id": rec["id"], "status": rec["status"], "customer": d.get("customer"), "thread": thread,
            "shipment": d.get("request"), "preference": d.get("preference"), "options": d.get("options"),
            "carrier_messages": d.get("carrier_messages"), "quote": d.get("quote"), "booking": d.get("booking"),
            "estimated_arrival": eta(d["booking"]) if d.get("booking") else None, "notes": d.get("notes")}


def mail_carrier(ctx: Ctx, to: str, subject: str, body: str, in_reply_to: int | None) -> dict:
    to = to.strip().lower()
    if to != RATEDESK and not kit.world().carrier_by_email(to):
        return {"error": f"{to} is not on our carrier list"}
    _ensure_deal(ctx)
    mid = ctx.fw.mail_carrier(ctx.deal_id, to, subject, body, in_reply_to=in_reply_to)
    store.update(ctx.deal_id, lambda r: (r["status"], {**r["data"], "asked": {**r["data"].get("asked", {}),
                                                                              str(mid): to}}))
    return {"sent": mid, "note": "their answer comes back into this deal"}


def carrier_status(ctx: Ctx, deal_id: str, question: str | None, wait_seconds: float) -> dict:
    rec = store.get(deal_id)
    b = (rec or {}).get("data", {}).get("booking")
    if not b:
        return {"error": f"{deal_id} has no booking"}
    air = (b.get("option") and (rec["data"].get("options") or {}).get(b["option"], {}).get("air")) or {}
    carrier = kit.world().carrier_by_name(b["airline"])
    to = air.get("email") or (carrier.email if carrier else None)
    if not to:
        return {"error": f"no mail address for {b['airline']}"}
    ref = b.get("booking_reference") or b.get("rate_id") or b["team_reference"]
    body = question or (f"Hello,\n\ncould you tell me the current status of our shipment {ref} ({b['route']}, "
                        f"{b.get('weight_kg')} kg, our reference {b['team_reference']})? Where is it now, and when do "
                        f"you expect it to arrive?\n\nThanks,\n{settings.persona}, {settings.company}")
    before = len(rec["data"].get("carrier_messages") or [])
    # in the airline's own booking thread when it confirmed by mail (its desk knows the booking there)
    thread = b.get("confirmation_mail") or air.get("reply_mail")
    subject = f"Re: Booking {ref} confirmed" if b.get("confirmation_mail") else f"Shipment status {ref}"
    mid = ctx.fw.mail_carrier(deal_id, to, subject, body, in_reply_to=thread)
    end = time.time() + max(0.0, float(wait_seconds))
    reply = None
    while time.time() < end:
        msgs = store.get(deal_id)["data"].get("carrier_messages") or []
        reply = next((x for x in msgs[before:] if x["from"].lower() == to.lower() and x["mail"] > mid), None)
        if reply:
            break
        ctx.fw.wait_step()
    facts = _summary(store.get(deal_id), store.get(f"booking-{rec['data']['root']}"))
    if not reply:
        return {"asked": mid, "carrier_reply": None, "note": "no answer yet; it will be stored on the deal when it "
                "comes (deal tool)", "booking": facts["booking"]}
    if re.search(r"to quote we need|please provide|we need:", reply["text"], re.I):
        return {"carrier_reply": reply["text"], "booking": facts["booking"],
                "note": "the airline answered with its quote form, not with a status (5U carriers did so on Sat "
                        "16:13 too). Answer from our record: expected_stage_now and the dates, as our estimates. "
                        "That is back-office detail: the customer needs the status, not how we got it."}
    status = {"text": reply["text"], "mail": reply["mail"], "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    store.update(deal_id, lambda r: (r["status"], {**r["data"], "booking": {**r["data"]["booking"],
                                                                           "carrier_status": status}}))
    bid = f"booking-{rec['data']['root']}"
    if store.get(bid):
        store.update(bid, lambda r: (r["status"], {**r["data"], "carrier_status": status}))
    return {"carrier_reply": reply["text"], "received": status["at"], "booking": facts["booking"]}


def note(ctx: Ctx, text: str, flag: str) -> dict:
    _ensure_deal(ctx)
    store.update(ctx.deal_id, lambda r: (r["status"], {**r["data"], "notes": r["data"].get("notes", []) + [
        {"at": time.time(), "text": text, "flag": flag}], "flag": flag if flag != "none" else r["data"].get("flag")}))
    store.log("forwarder", "decision", f"note [{flag}] {text[:160]}", run_id=ctx.deal_id)
    return {"ok": True}


def no_reply(ctx: Ctx, reason: str, done: bool = False) -> dict:
    ctx.done = ctx.done or bool(done)
    ctx.outcome.append("no_reply")
    store.log("forwarder", "decision", f"no reply: {reason[:160]}", run_id=ctx.deal_id)
    return {"ok": True}


# ---- helpers -----------------------------------------------------------------------------------------------

def _ensure_deal(ctx: Ctx) -> None:
    if store.get(ctx.deal_id) is None:
        first = store.thread(ctx.root)[0] if store.thread(ctx.root) else (ctx.mail or {})
        store.put(ctx.deal_id, "deal", "new", {"root": ctx.root, "customer": first.get("sender"),
                                               "subject": first.get("subject"), "received_at": first.get("received_at"),
                                               "offers": [], "asked": {}, "replied": []})


def _last_inbound(root: int) -> dict | None:
    return next((x for x in reversed(store.thread(root)) if x["direction"] == "in"), None)


def _summary(rec: dict, b: dict | None) -> dict:
    d = rec["data"]
    bd = (b or {}).get("data") or d.get("booking")
    return {"deal_id": rec["id"], "status": rec["status"], "customer": d.get("customer"), "subject": d.get("subject"),
            "shipment": d.get("request"), "quote": {k: (d.get("quote") or {}).get(k) for k in ("amount", "option")}
            if d.get("quote") else None,
            "booking": ({**{k: bd.get(k) for k in ("booking_reference", "team_reference", "rate_id", "airline", "route",
                                                   "transit_days", "status", "via", "pickup", "amount",
                                                   "carrier_status")},
                         "airline_email": getattr(kit.world().carrier_by_name(bd.get("airline") or ""), "email", None),
                         "booked_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(bd["booked_at"])),
                         "airline_confirmation": bd.get("confirmation_text"), **timeline(bd)} if bd else None)}


def timeline(booking: dict) -> dict:
    """Where a booked shipment should be now, from our dates (pricing.schedule, the same the quote used). Estimates,
    and the agent says so. The airline's word, when it gives one, wins (carrier_status)."""
    from datetime import datetime, timezone
    try:
        booked = datetime.fromtimestamp(booking["booked_at"], timezone.utc)
        pickup_h = float((booking.get("pickup") or {}).get("days") or 0) * 24
        ready, departure, arrival = pricing.schedule(booking.get("ready_date"), pickup_h, booking["transit_days"],
                                                     booked)
    except (KeyError, TypeError, ValueError):
        return {}
    now = datetime.now(timezone.utc)
    stage = ("booked, waiting for the goods to be ready" + (" and collected" if pickup_h else "")
             if now < ready else "collected, on its way to the airport" if now < departure
             else "in transit" if now < arrival else "arrived")
    return {"ready_date": ready.strftime(pricing.DATE), "estimated_departure": departure.strftime(pricing.DATE),
            "estimated_arrival": arrival.strftime(pricing.DATE), "expected_stage_now": stage}


def eta(booking: dict) -> str | None:
    return timeline(booking).get("estimated_arrival")


def _ts(iso: str | None) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else time.time()
    except ValueError:
        return time.time()
