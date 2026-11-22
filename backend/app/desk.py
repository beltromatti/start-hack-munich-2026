"""The desk's assistant: a person at the desk asks about their shipments, customers, carriers and prices.

An agent like the forwarder, smaller: the model decides what to read and when it knows enough, the system
guarantees. It reads the register through read-only tools (shipments, one shipment with its mails, customers,
the rate sheets on a lane) and answers in one structured reply. Our own OpenAI key (`llm.respond_direct`), never
the gateway: it is a person's tool, no part of a quote. What it returns is checked against the register before
the page sees it: a shipment id or customer it names must exist, and the one action it may propose, a message to
a shipment's session, happens only when a person clicks. No cap on steps or tokens; one stop for spinning.
"""
import json
import time
from decimal import Decimal

from . import llm, pricing, store
from .config import KIT

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["answer", "facts", "shipment_ids", "customer", "page", "action", "refused"],
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["label", "value"],
                                             "properties": {"label": {"type": "string"}, "value": {"type": "string"}}}},
        "shipment_ids": {"type": "array", "items": {"type": "string"}},
        "customer": {"type": ["string", "null"]},
        "page": {"type": "string", "enum": ["ship", "cust", "net", "none"]},
        "action": {"type": "object", "additionalProperties": False, "required": ["kind", "shipment_id", "text"],
                   "properties": {"kind": {"type": "string", "enum": ["none", "tell"]},
                                  "shipment_id": {"type": ["string", "null"]}, "text": {"type": ["string", "null"]}}},
        "refused": {"type": "boolean"},
    },
}
ONLY_THIS_DESK = "I can only help with this desk: shipments, customers, carriers, routes and prices."
SPINNING = 12  # model turns without a final answer: it is going round in circles, not working
_asked: list[float] = []  # a brake on a runaway page (30 questions a minute), not a budget


def _fn(name: str, description: str, properties: dict) -> dict:
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": llm.strict(properties)}


S, N = {"type": ["string", "null"]}, {"type": ["integer", "null"]}
TOOLS = [
    _fn("find_shipments", "Shipments in the register, newest first: status, customer, route, weight, the quote, the "
        "booking, Giulia's flag. Filter by words (customer, city or airport code, subject, booking reference) and by "
        "status, or leave both null for all of them.", {"text": S, "status": S, "limit": N}),
    _fn("read_shipment", "One shipment in full: the request as Giulia read it, the priced options, the quote, the "
        "booking, her notes, the customer's mails and what the carriers wrote.", {"shipment_id": {"type": "string"}}),
    _fn("customers", "Every customer on record: shipments, bookings, quoted value, the latest request, and the notes "
        "Giulia keeps for them.", {}),
    _fn("rate_sheets", "This month's airline rate sheets (EUR per kg by weight break, minimum, fuel and security per "
        "kg, transit days) on a lane or from an origin. Airport codes, such as FRA and ORD; either may be null. Give a "
        "weight (and a volume when known) and each lane carries its total in EUR, computed by our pricing code as on "
        "a quote: airport to airport, before pickup. A price you tell a person comes from here, never from your own "
        "arithmetic.", {"origin": S, "destination": S, "weight_kg": {"type": ["number", "null"]},
                        "volume_cbm": {"type": ["number", "null"]}}),
    _fn("desk_page", "What the desk page itself shows and computed from the same register: per customer and per "
        "carrier what it learned, such as reply times and notes. Empty when the page sent nothing.", {}),
]


def _row(r: dict) -> dict:
    d, req = r["data"], r["data"].get("request") or {}
    b = d.get("booking") or {}
    return {"id": r["id"], "status": r["status"], "customer": d.get("customer"), "subject": d.get("subject"),
            "received_at": d.get("received_at"),
            "route": f"{req.get('origin')} to {req.get('destination')}" if req.get("origin") else None,
            "weight_kg": req.get("weight_kg"), "preference": d.get("preference"),
            "quote_eur": (d.get("quote") or {}).get("amount"), "quoted_option": (d.get("quote") or {}).get("option"),
            "booking": {"reference": b.get("booking_reference"), "airline": b.get("airline"),
                        "status": b.get("status"), "amount": b.get("amount")} if b else None,
            "flag": d.get("flag"), "flag_note": next((n["text"] for n in reversed(d.get("notes") or []) if n.get("flag")), None)}


def _clip(s, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def _find(text: str | None, status: str | None, limit: int | None) -> list[dict]:
    words = [w for w in (text or "").lower().split() if w]
    rows = [_row(r) for r in store.records("deal", limit=5000)]
    rows = [x for x in rows if (not status or x["status"] == status)
            and all(w in json.dumps(x, ensure_ascii=False).lower() for w in words)]
    return rows[: limit or len(rows)]


def _shipment(shipment_id: str) -> dict:
    r = store.get(shipment_id)
    if not r or r["type"] != "deal":
        return {"error": f"no shipment {shipment_id}"}
    d = r["data"]
    mails = [{"direction": m["direction"], "from": m["sender"], "to": m["recipient"], "at": m.get("received_at"),
              "subject": m["subject"], "body": m["body"]} for m in store.thread(d["root"])]
    carriers = [{"from": m["sender"], "to": m["recipient"], "subject": m["subject"], "body": m["body"]}
                for m in store.carrier_mails(shipment_id)]
    return {**_row(r), "request": d.get("request"), "options": d.get("options"), "quote": d.get("quote"),
            "booking": d.get("booking"), "notes": d.get("notes"), "customer_mails": mails, "carrier_mails": carriers}


def _customers() -> list[dict]:
    out: dict[str, dict] = {}
    for r in store.records("deal", limit=5000):
        d = r["data"]
        c = out.setdefault(d.get("customer") or "?", {"customer": d.get("customer"), "shipments": 0, "booked": 0,
                                                      "quoted_eur": Decimal(0), "latest": None, "notes": []})
        c["shipments"] += 1
        c["booked"] += r["status"] == "booked"
        if (d.get("quote") or {}).get("amount"):
            c["quoted_eur"] += Decimal(str(d["quote"]["amount"]))
        c["latest"] = max(filter(None, [c["latest"], d.get("received_at")]), default=None)
        c["notes"] += [n["text"] for n in d.get("notes") or [] if n.get("text") not in c["notes"]]
    return [{**c, "quoted_eur": str(c["quoted_eur"])} for c in out.values()]


def _sheets(origin: str | None, destination: str | None, kg=None, cbm=None) -> list[dict]:
    lanes = json.loads((KIT / "tariffs.json").read_text())["lanes"]
    o, t = (origin or "").upper(), (destination or "").upper()
    out = [x for x in lanes if (not o or x["origin"] == o) and (not t or x["destination"] == t)]
    if kg:
        for x in out:
            total, billed = pricing.sheet_price(x, Decimal(str(kg)), Decimal(str(cbm)) if cbm else None)
            x.update(total_eur=str(total), billed_kg=str(billed))
    return out


def run(name: str, args: dict, page: dict) -> object:
    if name == "find_shipments":
        return _find(args.get("text"), args.get("status"), args.get("limit"))
    if name == "read_shipment":
        return _shipment(str(args.get("shipment_id") or ""))
    if name == "customers":
        return _customers()
    if name == "rate_sheets":
        return _sheets(args.get("origin"), args.get("destination"), args.get("weight_kg"), args.get("volume_cbm"))
    if name == "desk_page":
        return page or {}
    return {"error": f"no tool {name}"}


def checked(out: dict) -> dict:
    """What the page may show of the model's answer: only shipments and customers that exist in the register."""
    deals = {r["id"]: r["data"].get("customer") for r in store.records("deal", limit=5000)}
    refused = bool(out.get("refused"))
    a = out.get("action") or {}
    act = None
    if not refused and a.get("kind") == "tell" and str(a.get("shipment_id")) in deals and _clip(a.get("text"), 600):
        act = {"kind": "tell", "deal": str(a["shipment_id"]), "text": " ".join(str(a["text"]).split())}
    return {
        "text": str(out.get("answer") or "").strip() or ONLY_THIS_DESK, "refused": refused,
        "facts": [] if refused else [[_clip(f.get("label"), 60), _clip(f.get("value"), 200)]
                                     for f in out.get("facts") or []],
        "rows": [] if refused else [i for i in map(str, out.get("shipment_ids") or []) if i in deals],
        "customer": str(out["customer"]) if not refused and out.get("customer") in set(deals.values()) else None,
        "page": out.get("page") if not refused and out.get("page") in ("ship", "cust", "net") else None,
        "act": act,
    }


def answer(question: str, desk: dict | None = None, earlier: list | None = None) -> dict:
    question = " ".join(str(question or "").split())
    if not question:
        raise ValueError("empty question")
    now = time.time()
    _asked[:] = [t for t in _asked if now - t < 60]
    if len(_asked) >= 30:
        raise RuntimeError("too many questions for a minute")
    _asked.append(now)
    turns = [(str(t.get("q") or ""), str(t.get("a") or "")) for t in (earlier or []) if isinstance(t, dict)]
    before = "".join(f"Person: {q}\nYou: {a}\n" for q, a in turns if q and a)
    items: list[dict] = [{"role": "user", "content": (
        (f"EARLIER IN THIS CONVERSATION (for what 'it' or 'they' refers to):\n{before}\n" if before else "")
        + f"QUESTION FROM THE PERSON AT THE DESK:\n{question}")}]
    for _ in range(SPINNING):
        out = llm.respond_direct(llm.prompt("desk"), items, TOOLS, schema=SCHEMA, name="desk_answer")
        items += out
        calls = [i for i in out if i.get("type") == "function_call"]
        if not calls:
            text = "".join(c.get("text", "") for i in out if i.get("type") == "message" for c in i.get("content") or [])
            return checked(json.loads(text or "{}"))
        for c in calls:
            try:
                result = run(c["name"], json.loads(c.get("arguments") or "{}"), desk or {})
            except Exception as e:  # a tool that fails tells the model why, as the forwarder's tools do
                result = {"error": repr(e)[:300]}
            items.append({"type": "function_call_output", "call_id": c["call_id"],
                          "output": json.dumps(result, ensure_ascii=False, default=str)})
    raise RuntimeError("the assistant went round in circles")
