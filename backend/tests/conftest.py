import re
import sqlite3

import pytest

from app import kit, llm, store


def fake_llm(name, system, user, schema):
    if name == "customer":
        last = user.split("--- mail")[-1]
        intent = "accept" if re.search(r"\b(accept|book it|go ahead)\b", last, re.I) else "new_request"
        kg = re.search(r"(\d+(?:\.\d+)?)\s*kg", user)
        cbm = re.search(r"(\d+(?:\.\d+)?)\s*cbm", user)
        route = re.search(r"\b([A-Z]{3})\b to \b([A-Z]{3})\b", user)
        post = re.search(r"\b(\d{5})\b", user)
        return {"intent": intent, "customer_name": "Anna", "company": "Acme", "language": "en",
                "origin_airport": route.group(1) if route else None, "pickup_needed": bool(post),
                "pickup_postcode": post.group(1) if post else None, "pickup_city": None,
                "destination_airport": route.group(2) if route else None, "destination_city": None,
                "pieces": 2, "weight": {"value": float(kg.group(1)) if kg else None, "unit": "kg", "per_piece": False},
                "volume": {"value": float(cbm.group(1)) if cbm else None, "unit": "cbm", "per_piece": False},
                "dimensions": [], "preference": "fastest" if "fast" in user.lower() else "cheapest",
                "ready_date": None, "commodity": "machine parts", "flags": [], "missing": [], "references": [],
                "notes": None}
    if name == "bid":
        if "do not serve" in user:
            return {"offers": [{"carrier": "x", "airline_code": None, "available": False, "total": None,
                                "currency": None, "transit_days": None, "pickup_hours": None, "reference": None,
                                "valid_until": None, "note": None}]}
        total = re.search(r"(\d+\.\d{2}) EUR", user)
        days = re.search(r"(\d+) days", user)
        hours = re.search(r"(\d+) hours", user)
        ref = re.search(r"\b(R-\S+?|TRK-\d+)\b", user)
        return {"offers": [{"carrier": re.search(r"From: (\S+)", user).group(1), "airline_code": None,
                            "available": True, "total": float(total.group(1)) if total else None, "currency": "EUR",
                            "transit_days": int(days.group(1)) if days else None,
                            "pickup_hours": int(hours.group(1)) if hours else None,
                            "reference": ref.group(1) if ref else None, "valid_until": None, "note": None}]}
    if name == "write":
        amount = re.search(r"amount: (.+)", user).group(1)
        return {"body": f"Hi Anna,\n\nall-in {amount}.\n\nGiulia" if amount != "none" else "Hi Anna,\n\ndone.\n\nGiulia"}
    raise AssertionError(name)


@pytest.fixture(autouse=True)
def world():
    store.use_connection(sqlite3.connect(":memory:", check_same_thread=False))
    llm.use_fake(fake_llm)
    w = kit.load()
    yield w
    llm.use_fake(None)
