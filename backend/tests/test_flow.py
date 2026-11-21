"""The whole forwarder against the fake 5U: rfq -> bids -> one quote -> accept -> booking -> tracking."""
from app import kit, store
from app.fake5u import FakeFiveU
from app.forwarder import Forwarder


class Sync(Forwarder):
    """Runs jobs inline so the test is deterministic."""
    def submit(self, key, fn, *args):
        if key in ("portal", "board"):
            return
        fn(*args)


def run(f, n=3):
    for _ in range(n):
        f.tick()


def test_rfq_quote_book_track(monkeypatch):
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("anna@acme.example", "Quote FRA to ORD",
                       "Hi, please quote 320 kg, 1.5 cbm, FRA to ORD, cheapest please. Anna")
    run(f)
    quotes = [m for m in api.outbox if m["to"] == "anna@acme.example"]
    assert len(quotes) == 1, "exactly one quote"
    q = quotes[0]
    assert q["in_reply_to"] == rfq["id"]
    rec = store.get(f"rfq-{rfq['id']}")
    assert rec["status"] == "quoted"
    totals = sorted(float(o["total"]) for o in rec["data"]["offers"] if o["leg"] == "air")
    assert rec["data"]["amount"] == f"{totals[0]:.2f} EUR"  # cheapest of portal, sheet and mail bids
    assert rec["data"]["amount"] in q["body"]
    run(f)
    assert len([m for m in api.outbox if m["to"] == "anna@acme.example"]) == 1, "never quote twice"

    api.customer("anna@acme.example", "Re: Quote FRA to ORD", "Great, go ahead and book it. Anna", in_reply_to=q["id"])
    run(f)
    booking = store.get(f"booking-{rfq['id']}")
    assert booking and booking["status"] in ("booked", "requested", "confirmed")
    assert store.get(f"rfq-{rfq['id']}")["status"] == "booked"

    ref = booking["data"].get("booking_reference") or booking["data"]["team_reference"]
    api.customer("tracking@hackloop.mail", f"Where is {ref}?", f"Hello, where is shipment {ref}?")
    run(f)
    answers = [m for m in api.outbox if m["to"] == "tracking@hackloop.mail"]
    assert len(answers) == 1


def test_door_to_port_waits_for_truckers_and_adds_pickup(monkeypatch):
    api = FakeFiveU(reply_now=False)
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("bob@beta.example", "Pickup in 60311",
                       "Pickup at 60311 Frankfurt, 320 kg, 1.5 cbm, FRA to ORD, fastest.")
    run(f, 2)
    assert store.get(f"rfq-{rfq['id']}")["status"] == "collecting"
    api.flush()
    run(f, 3)
    rec = store.get(f"rfq-{rfq['id']}")
    assert rec["status"] == "quoted"
    assert rec["data"]["quote"]["pickup"]["carrier"]
    assert rec["data"]["request"]["pickup_zone"] == "60"


def test_tariff_mail_replaces_the_airlines_sheet():
    from decimal import Decimal
    from app import llm
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    lane = {"origin": "FRA", "destination": "ORD", "transit_days": 3, "minimum": "EUR 99.00",
            "breaks_kg": [0, 45, 100, 250, 500, 1000, 2000], "rates_per_kg": ["9", "8", "7", "6", "5", "4", "3"],
            "fuel_per_kg": "1,00", "security_per_kg": "0.10"}
    prev = llm._fake
    llm.use_fake(lambda name, *a: {"airline": None, "currency": "EUR", "valid_from": None, "valid_to": None,
                                   "notes": None, "lanes": [lane]} if name == "tariff" else prev(name, *a))
    api._deliver("yellowtail-air-freight@hackloop.mail", api.mailbox, "Tariff December 2026", "New rates attached.")
    run(f, 2)
    yl = [l for l in kit.world().sheet("FRA", "ORD") if l["airline"] == "Yellowtail Air Freight"]
    assert len(yl) == 1 and yl[0]["minimum_eur"] == "99.00" and yl[0]["fuel_eur_per_kg"] == "1.00"
    assert [l for l in kit.world().sheet_lanes if l["airline"] == "Yellowtail Air Freight"] == yl
    assert store.get("tariff-yellowtail-air-freight")["status"] == "active"
