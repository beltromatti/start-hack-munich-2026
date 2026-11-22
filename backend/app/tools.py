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

from . import kit, pricing, store
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
            "weight": {**QUANTITY, "description": "gross weight of this lot as written (never net): value, unit (kg, "
                                                  "lb, t), per_piece true if it is the weight of one piece ('each', "
                                                  "'à', 'je'). Null values when only a weight for all lots together "
                                                  "is given (that goes in totals)"},
            "volume": {**QUANTITY, "description": "as written: value, unit (cbm, cft, l), per_piece true when it is "
                                                  "one piece's ('8 cartons à 22 kg and 0.25 cbm': 0.25 per piece); "
                                                  "null values if not given"},
            "dimensions": nullable(obj({"length": N, "width": N, "height": N, "unit": S},
                                       "size of ONE piece of this lot, as written. A Euro pallet is 120 x 80 cm and "
                                       "an industrial pallet 120 x 100 cm: with the height they give, that is its size")),
        })},
    "totals": nullable(obj({"weight": QUANTITY, "volume": QUANTITY},
                           "a weight or volume the customer gives for ALL the lots together ('2 different pallets, "
                           "480 kg in total'): here, once, and the lots' own weight or volume null. Null when every "
                           "lot has its own")),
    "cargo": obj({"commodity": S, "ready_date": S, "notes": S}),
    "insurance": nullable(obj({
        "goods_value": {**N, "description": "the value of the goods as written"},
        "currency": {**S, "description": "of the goods value, as written (EUR if they say nothing)"},
        "insured_percent": {**N, "description": "share of the value insured, as written (110 for '110 % of the "
                                                 "value'); null when they do not say: 100"},
        "premium_percent": {**N, "description": "premium rate in percent, as written (0.40 for '0.40 %')"},
        "minimum_premium": {**N, "description": "a minimum premium if they name one, else null"}},
        "cargo insurance the customer wants in the all-in price, on the terms they give: our code adds the premium "
        "to every option's total. null when they do not ask for insurance")),
    "extra_charges": {"type": "array", "description": (
        "other charges the customer tells us to include in the all-in price, with the amount or rate they give "
        "(their broker's customs fee, a handling fee in their frame agreement): our code adds each to every option's "
        "total. Empty when they name none; never a charge they did not state"),
        "items": obj({"label": {"type": "string"},
                      "amount": {**N, "description": "the amount or rate as written"},
                      "currency": {**S, "description": "as written (EUR if they say nothing); null for a percent"},
                      "basis": {"type": "string", "enum": ["per_shipment", "per_kg", "percent_of_freight"],
                                "description": "per_kg: per chargeable kg; percent_of_freight: percent of the "
                                               "all-in freight total before these charges"}})},
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
        "option_id": S, "to": S, "done": DONE,
        "offer_pdf": {"type": "boolean", "description": "true attaches our offer for option_id as a pdf (made by "
                      "code from the option: route, airline, transit, pickup, goods, estimated dates, the one total), "
                      "for a customer who wants the offer as a document (for their purchasing or files). false "
                      "otherwise."}}),
    fn("book",
       "Book an option of this deal with the carrier: by its rate reference on the portal (a fresh rate if it "
       "expired), otherwise by mail to the airline. Returns the booking with its reference and status. deal_id: "
       "null for this thread's deal; the offer's own deal (crm finds it) when the customer accepts in a new mail "
       "an offer we made them in another thread, because its options live there.",
       {"option_id": {"type": "string"}, "deal_id": S}),
    fn("cancel_booking",
       "Cancel one of our bookings with 5U when the customer (or the team) asks to cancel: it works for portal and "
       "mail bookings alike, before or after the airline's confirmation, and the shipment is then no longer booked. "
       "The airline needs no mail. deal_id: null for this thread's deal, else the booking's own deal (crm finds it).",
       {"booking_reference": {"type": "string"}, "deal_id": S}),
    fn("browser",
       "A browser page for this deal, shared with the team (they see it live in the deal's conversation), on 5U's "
       "sites only: today 5U's portal page, where the rates of airlines whose rate API answers 503 still are, for "
       "people who pass its check. action: open (url, or null for the portal page: the visible form by index and "
       "label, and the text); read (the page now, and a rate if it shows one); fill (fields: [{i, value}] by the "
       "index the form shows; for the team key pass the value {team_key}: the person types it with a click); press "
       "(i: a visible button, e.g. a cookie banner's privacy-friendly choice, a popup's close). Pages change their "
       "fields at every load: read the labels, never assume.",
       {"action": {"type": "string", "enum": ["open", "read", "fill", "press"]}, "url": S,
        "fields": {"type": ["array", "null"], "items": obj({"i": {"type": "integer"}, "value": {"type": "string"}})},
        "i": I}),
    fn("ask_person",
       "Interrupt the team for what only a person can do, when one is at the desk (operator mode): an alarm rings and "
       "this deal opens in front of them. kind page: they act on this deal's browser page (pass a check, type the "
       "key, send); it waits for the page to show a rate and adds it to this deal's prices for `airline`. kind "
       "answer: they answer `note` in words (a decision, a fact you cannot get), and you get their answer. Waits up to "
       "wait_seconds (the quote is due within 2 minutes of the request). Nobody is asked when operator mode is off.",
       {"kind": {"type": "string", "enum": ["page", "answer"]}, "note": {"type": "string"}, "airline": S,
        "wait_seconds": {"type": "number"}}),
    fn("crm",
       "Search our CRM: deals and bookings by booking or rate reference, our reference (SM-...), customer name or "
       "address, company, route, airline, anything. Returns the matching deals with their shipment, quote, booking, "
       "status and dates (estimated arrival computed). Empty query: the latest deals.",
       {"query": {"type": "string"}}),
    fn("deal",
       "The whole record of a deal: the thread, the shipment, every offer and carrier message, the options, the "
       "quote, the booking, notes. No id: the deal of this thread.",
       {"deal_id": S}),
    fn("mail_carrier",
       "Write to a carrier or trucker from our carrier list, or to the rate desk: to answer a question they asked, "
       "to ask for something, to book by mail, to cancel. One clear mail says it all; an automatic reply is not a "
       "reason to write again (twice in 10 minutes per carrier is the most this tool sends). Their answer comes "
       "back into this deal (get_offers with shipment null waits for it). in_reply_to: the id of their mail you "
       "answer, if any.",
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
    f = {"get_offers": get_offers, "send_mail": send_mail, "book": book, "cancel_booking": cancel_booking,
         "browser": browser, "ask_person": ask_person,
         "crm": crm, "deal": deal,
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
    if out.get("missing"):
        store.update(ctx.deal_id, lambda r: ("waiting_customer", r["data"]))
    return out


def send_mail(ctx: Ctx, kind: str, body: str, option_id: str | None, to: str | None, done: bool = False,
              offer_pdf: bool = False) -> dict:
    attachments = None
    if offer_pdf:
        doc = _offer_document(ctx, option_id)
        if isinstance(doc, str):
            return {"error": doc}
        attachments = [doc]
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
    sent = ctx.fw.api.send(to, subject, body, in_reply_to=parent["id"], attachments=attachments)
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


def _offer_document(ctx: Ctx, option_id: str | None) -> dict | str:
    """Our offer for one option as a pdf attachment, every fact and the one total from the deal's record (code, like
    every price): what the mail says, on paper for the customer's files. A str when there is no such option."""
    import base64
    from datetime import datetime, timezone
    from . import docs
    d = (store.get(ctx.deal_id) or {}).get("data") or {}
    opt = (d.get("options") or {}).get(option_id or "")
    if not opt:
        return f"offer_pdf needs the option_id of an option of this deal ({option_id!r} is none)"
    req, air, pick = opt.get("request") or d.get("request") or {}, opt["air"], opt.get("pickup")
    ref = f"SM-{d.get('root', ctx.root)}"
    ready, leaves, arrives = pricing.schedule(req.get("ready_date"), float(pick["days"]) * 24 if pick else 0, air["days"])
    def plain(x):  # 2.000 -> 2, 656.310 -> 656.31: a number as a person writes it
        return f"{pricing.Decimal(str(x)).normalize():f}"
    days = plain(air["days"])
    goods = ", ".join(x for x in (f"{req['pieces']} pieces" if req.get("pieces") else "",
                                  f"{plain(req['weight_kg'])} kg" if req.get("weight_kg") else "",
                                  f"{plain(req['volume_cbm'])} cbm" if req.get("volume_cbm") else "",
                                  req.get("commodity") or "") if x)
    lines = [f"{settings.company}, {datetime.now(timezone.utc).strftime('%d %b %Y')}",
             f"For: {d.get('customer') or ''}",
             f"Your request: {d.get('subject') or ''}", "",
             (f"Pickup: {pick['carrier']} collects at postcode {req.get('pickup_postcode') or req.get('pickup_zone')} "
              f"and brings the goods to {req.get('origin')} airport" if pick else
              f"Airport to airport: {req.get('origin')} to {req.get('destination')}"),
             f"Air freight: {air['carrier']}, {req.get('origin')} to {req.get('destination')}, "
             f"{days} day{'' if days == '1' else 's'} in transit",
             f"Goods: {goods}" if goods else "",
             f"Chargeable weight: {plain(air.get('billed_kg') or req.get('chargeable_kg'))} kg",
             f"Goods ready: {ready.strftime(pricing.DATE)}",
             f"Estimated departure: {leaves.strftime(pricing.DATE)}",
             f"Estimated arrival: {arrives.strftime(pricing.DATE)}", "",
             f"Total all-in: {opt['total_text']}", "",
             "The total includes the air freight with its surcharges" + (" and the pickup." if pick else "."),
             "Dates are estimates from the ready date, the pickup time and the airline's transit time.",
             "To book, a short yes to our mail is enough.", "",
             f"{settings.persona}, {settings.company}"]
    raw = docs.pdf(f"Air freight offer {ref}", [x for x in lines if x is not None])
    return {"filename": f"offer-{ref}.pdf", "content_type": "application/pdf",
            "content_base64": base64.b64encode(raw).decode()}


MONEY = re.compile(r"(?:€|\$|£|\b(?:EUR|USD|GBP|CHF)\b)\s*\d[\d.,']*|\d[\d.,']*\s*(?:€|\$|£|\b(?:EUR|USD|GBP|CHF|euros?|dollars?)\b)",
                   re.IGNORECASE)


def _quote_amounts(ctx: Ctx, option_id: str | None, body: str) -> str | None:
    """None when the quote carries exactly one amount of money, the option's total. Else what to change."""
    d = store.get(ctx.deal_id)["data"] if store.get(ctx.deal_id) else {}
    opt = (d.get("options") or {}).get(option_id or "")
    if not opt:
        return None  # no option to check against (recorded as such by _record_quote)
    found = MONEY.findall(re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))", "", body))  # 6 270,02 is one amount
    if body.count(opt["total_text"]) == 1 and len(found) == 1:
        return None
    return (f"a quote carries exactly one amount of money, the total of option {option_id} written as "
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


def book(ctx: Ctx, option_id: str, deal_id: str | None = None) -> dict:
    """A customer who accepts in a new mail instead of a reply opens a new thread, whose deal has no options: the
    offer lives on the deal of the thread we quoted in. That deal can be booked from here when it is this
    customer's own (the same permission as `deal` and `crm`)."""
    _ensure_deal(ctx)
    if deal_id and deal_id != ctx.deal_id:
        rec = store.get(deal_id)
        if not rec or rec["type"] != "deal":
            return {"error": "no such deal"}
        # seeing a deal is not the right to book it: only the customer the offer was made to, writing now, in a
        # customer thread (the tracking desk sees every deal and books none)
        writer = (ctx.mail or _last_inbound(ctx.root) or {}).get("sender")
        owner = rec["data"].get("customer")
        if ctx.task != "customer" or not owner or writer != owner or not _visible(ctx, rec):
            return {"error": "that deal belongs to another customer"}
        return ctx.fw.book_option(deal_id, option_id)
    out = ctx.fw.book_option(ctx.deal_id, option_id)
    if out.get("error") and not out.get("options"):
        out["hint"] = ("this thread's deal has no priced options. If they accept an offer from another thread of "
                       "theirs, find its deal with crm and pass its deal_id")
    return out


PORTAL_PAGE = "https://start-hack.5u.ai/portal/ui"
BROWSER = "http://127.0.0.1:8010"


def _browser(method: str, path: str, body: dict | None = None) -> dict:
    import httpx
    try:
        r = httpx.request(method, BROWSER + path, json=body, timeout=30)
        return r.json() if r.status_code < 400 else {"error": f"browser {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": f"the shared browser is not running ({e!r})"[:200]}


def browser(ctx: Ctx, action: str, url: str | None = None, fields: list | None = None, i: int | None = None) -> dict:
    """The agent's hands on a page the team sees live. Only 5U's sites (the guarantee); keys stay with the person;
    a rate the page shows is read by code (read_portal_page), never by the model's arithmetic."""
    from urllib.parse import urlparse
    from .forwarder import read_portal_page
    _ensure_deal(ctx)
    deal = ctx.deal_id
    if action == "open":
        target = url or PORTAL_PAGE
        host = urlparse(target).hostname or ""
        if urlparse(target).scheme != "https" or not (host == "5u.ai" or host.endswith(".5u.ai")):
            return {"error": "the browser opens 5U's sites only (https, *.5u.ai)"}
        return _browser("POST", f"/pages/{deal}", {"url": target})
    if action == "fill":
        return _browser("POST", f"/pages/{deal}/fill", {"fields": {str(f["i"]): f["value"] for f in fields or []}})
    if action == "press":
        return _browser("POST", f"/pages/{deal}/press", {"i": i})
    if action == "read":
        out = _browser("GET", f"/pages/{deal}")
        return {**out, "rate": read_portal_page(out.get("text", ""))} if "text" in out else out
    return {"error": f"unknown action {action}"}


def ask_person(ctx: Ctx, kind: str, note: str, airline: str | None = None, wait_seconds: float = 60) -> dict:
    """An interruption to the team (like SIEVER's `avvisa`): the agent decides it, the system guarantees it (alarm,
    the deal opened in front of them, their answer back here). Only while someone is at the desk."""
    from .forwarder import OPERATOR_WAIT, _since, add_portal_page_rate, read_portal_page
    _ensure_deal(ctx)
    deal = ctx.deal_id
    if store.kv_get("operator_on") != "1":
        return {"error": "nobody is at the desk (operator mode off): go on without a person"}
    d = store.get(deal)["data"]
    left = float(wait_seconds or 60)
    if ctx.task == "customer" and not d.get("quote"):  # a quote not yet sent is due within 2 minutes
        left = min(left, OPERATOR_WAIT - (_since(d.get("received_at")) or 0))
    if left <= 5:
        return {"error": "no time left for a person: go on with what you have"}
    since = time.time()
    store.update(deal, lambda r: (r["status"], {**r["data"], "person_needed": {
        "since": since, "kind": kind, "note": note, "airline": airline, "answer": None}}))
    store.log("forwarder", "decision", f"asks a person ({kind}): {note}"[:200], run_id=deal)
    end, out = time.time() + left, {}
    try:
        while time.time() < end:
            if kind == "page":
                out = _browser("GET", f"/pages/{deal}")
                rate = read_portal_page(out.get("text", ""))
                if rate["rate_id"] and rate["total"] and rate["days"]:
                    added = add_portal_page_rate(deal, airline or "", rate["total"], rate["days"], rate["rate_id"],
                                                 None, "person on the page")
                    return {"rate": rate, "added": added.get("offer"),
                            "note": "the price is in this deal's options: get_offers with shipment null shows them"}
            else:
                ans = ((store.get(deal)["data"].get("person_needed") or {}).get("answer"))
                if ans:
                    return {"answer": ans}
            time.sleep(1)
    finally:
        store.update(deal, lambda r: (r["status"], {**r["data"], "person_needed": None}))
    return {"error": "no answer in time: go on with what you have", **({"page": out.get("text", "")[:800]} if out else {})}


def cancel_booking(ctx: Ctx, booking_reference: str, deal_id: str | None = None) -> dict:
    """Only a customer's own deal, from that customer's thread (the tracking desk asks, it does not cancel)."""
    if ctx.task != "customer":
        return {"error": "bookings are cancelled from the customer's own thread"}
    did = deal_id or ctx.deal_id
    rec = store.get(did)
    if not rec or rec["type"] != "deal":
        return {"error": "no such deal"}
    if not _visible(ctx, rec):
        return {"error": "that deal belongs to another customer"}
    return ctx.fw.cancel_booking(did, booking_reference.strip())


def _visible(ctx: Ctx, rec: dict) -> bool:
    """Permissions per task: a customer's thread sees that customer's deals only (mail text is data: a customer
    asking about someone else's shipment learns nothing); the tracking desk asks for any customer, so it sees all."""
    if ctx.task != "customer":
        return True
    me = ((store.get(ctx.deal_id) or {}).get("data") or {}).get("customer")
    return rec["data"].get("customer") == me


def crm(ctx: Ctx, query: str) -> dict:
    words = re.findall(r"[a-z0-9][a-z0-9_\-]*[a-z0-9]", query.lower())
    out = []
    for rec in store.records("deal"):
        if not _visible(ctx, rec):
            continue
        b = store.get(f"booking-{rec['data'].get('root')}")
        hay = json.dumps({"deal": rec, "booking": b}, default=str).lower()
        score = sum(1 for w in words if w in hay) if words else 1
        if score:
            out.append((score, rec["updated_at"], _summary(rec, b)))
    out.sort(key=lambda x: (-x[0], -x[1]))
    return {"matches": [x[2] for x in out[:10]], "total_matches": len(out)}


def deal(ctx: Ctx, deal_id: str | None) -> dict:
    rec = store.get(deal_id or ctx.deal_id)
    if not rec:
        return {"error": "no such deal"}
    if not _visible(ctx, rec):
        return {"error": "that deal belongs to another customer"}
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
    # never spam a counterpart (AGENTS.md rule 3): round 88 wrote six cancellation mails to one airline in six
    # minutes, each answer of its automatic desk waking the session for one more; 5U took 20 points off that round
    recent = [x for x in (store.get(ctx.deal_id)["data"].get("agent_mails") or [])
              if x["to"] == to and time.time() - x["at"] < 600]
    if len(recent) >= 2:
        return {"error": f"you already wrote to {to} twice in the last 10 minutes in this deal: more mails read as "
                         "spam to a carrier and to 5U. Their answer comes back here; meanwhile tell the customer "
                         "plainly what you know and what you are waiting for"}
    mid = ctx.fw.mail_carrier(ctx.deal_id, to, subject, body, in_reply_to=in_reply_to)
    store.kv_set(f"agentmail:{mid}", ctx.deal_id)  # the agent's own question: after a booking its answer is news
    store.update(ctx.deal_id, lambda r: (r["status"], {**r["data"], "agent_mails": (r["data"].get("agent_mails") or [])
                                                       + [{"to": to, "at": time.time(), "mail": mid}]}))
    store.update(ctx.deal_id, lambda r: (r["status"], {**r["data"], "asked": {**r["data"].get("asked", {}),
                                                                              str(mid): to}}))
    booked = bool((store.get(ctx.deal_id) or {}).get("data", {}).get("booking"))
    return {"sent": mid, "note": "the deal is booked: their answer goes on the booking and comes back to you here"
            if booked else "their answer comes back into this deal"}


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
            # what changed after the booking lives in the notes (round 88: the customer cancelled; the airline's
            # quote desk cannot): a tracking answer must see it next to the airline's word
            "notes": [n["text"] for n in d.get("notes", [])][-4:] or None,
            # a deal that booked more than one shipment: each one, as its own record holds it now
            "all_bookings": [{k: (store.get(f"booking-{x['team_reference'][3:]}") or {"data": x})["data"].get(k)
                              for k in ("booking_reference", "team_reference", "airline", "route", "weight_kg",
                                        "ready_date", "status")} for x in d.get("bookings") or []]
            if len(d.get("bookings") or []) > 1 else None,
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
    if booking.get("status") == "cancelled":  # cancelled at the customer's request: it is going nowhere
        stage = "cancelled at the customer's request: not shipping"
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
