import json
import re
import sqlite3

import pytest

from app import kit, llm, store


def fake_llm(name, system, user, schema):
    """The small model that reads carrier replies (and tariffs) for the tools."""
    if name == "bid":
        if "do not serve" in user:
            return {"offers": [{"carrier": "x", "airline_code": None, "available": False, "total": None,
                                "currency": None, "transit_days": None, "pickup_hours": None, "reference": None,
                                "valid_until": None, "note": None}]}
        if "confirmed" in user.lower():
            return {"offers": []}
        total = re.search(r"(\d+\.\d{2}) EUR", user)
        days = re.search(r"(\d+) days", user)
        hours = re.search(r"(\d+) hours", user)
        ref = re.search(r"\b(R-\S+?|TRK-\d+)\b", user)
        return {"offers": [{"carrier": re.search(r"From: (\S+)", user).group(1), "airline_code": None,
                            "available": True, "total": float(total.group(1)) if total else None, "currency": "EUR",
                            "transit_days": int(days.group(1)) if days else None,
                            "pickup_hours": int(hours.group(1)) if hours else None,
                            "reference": ref.group(1) if ref else None, "valid_until": None, "note": None}]}
    raise AssertionError(name)


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"c{abs(hash((name, json.dumps(args))))}", "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}]}


def fake_agent(messages, tools):
    """A scripted forwarder: enough to drive the harness and the tools through a whole deal."""
    last = messages[-1]
    if last["role"] == "tool":
        prev = next(m for m in reversed(messages) if m["role"] == "assistant")
        name = prev["tool_calls"][0]["function"]["name"]
        out = json.loads(last["content"])
        if name == "get_offers":
            if out.get("missing"):
                return call("send_mail", kind="question", body="Could you send the weight?", option_id=None, to=None)
            opt = out["recommended"]
            total = next(o["total"] for o in out["options"] if o["option"] == opt)
            return call("send_mail", kind="quote", body=f"Hi Anna,\n\nTotal: {total} all-in\n\nGiulia",
                        option_id=opt, to=None)
        if name == "book":
            return call("send_mail", kind="booking_confirmation",
                        body=f"Booked: {out.get('booking_reference') or out.get('team_reference')}", option_id=None, to=None)
        if name == "crm":
            m = out["matches"][0] if out["matches"] else None
            return call("send_mail", kind="tracking_answer",
                        body=f"Arrives {m['booking']['estimated_arrival']}" if m else "Which reference?",
                        option_id=None, to=None)
        return {"role": "assistant", "content": "done"}
    text = last["content"]
    if "Update from the system" in text:
        ref = re.search(r"booking reference (\S+)", text)
        return call("send_mail", kind="booking_confirmation", body=f"Confirmed: {ref.group(1)}", option_id=None, to=None)
    if "tracking desk" in messages[1]["content"] and len(messages) == 2:
        ref = re.search(r"\b(BK-\S+|SM-\d+)", text)
        return call("crm", query=ref.group(1) if ref else text[-80:])
    if re.search(r"book it|go ahead", text, re.I):
        deal = re.search(r"(A\d+f?)", json.dumps([m for m in messages if m["role"] == "tool"]))
        quoted = next(json.loads(m["function"]["arguments"])["option_id"] for x in messages if x["role"] == "assistant"
                      for m in x.get("tool_calls") or [] if m["function"]["name"] == "send_mail"
                      and json.loads(m["function"]["arguments"])["kind"] == "quote")
        return call("book", option_id=quoted)
    kg = re.search(r"(\d+(?:\.\d+)?)\s*kg", text)
    cbm = re.search(r"(\d+(?:\.\d+)?)\s*cbm", text)
    route = re.search(r"\b([A-Z]{3}) to ([A-Z]{3})\b", text)
    post = re.search(r"\b(\d{5})\b", text)
    shipment = {"origin_airport": route.group(1) if route else None,
                "pickup": {"postcode": post.group(1), "city": None} if post else None,
                "destination_airport": route.group(2) if route else None, "pieces": 2,
                "weight": {"value": float(kg.group(1)) if kg else None, "unit": "kg", "per_piece": False},
                "volume": {"value": float(cbm.group(1)) if cbm else None, "unit": "cbm", "per_piece": False},
                "dimensions": [], "cargo": {"commodity": None, "ready_date": None, "notes": None}}
    pref = "fastest" if "fast" in text.lower() else "cheapest"
    return call("get_offers", shipment=shipment, preference=pref, wait_seconds=5)


@pytest.fixture(autouse=True)
def world():
    store.use_connection(sqlite3.connect(":memory:", check_same_thread=False))
    llm.use_fake(fake_llm)
    llm.use_fake_chat(fake_agent)
    w = kit.load()
    yield w
    llm.use_fake(None)
    llm.use_fake_chat(None)
