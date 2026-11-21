"""The forwarder agent against the fake 5U, driven by a scripted model: quote -> accept -> book -> track."""
from app import kit, store
from app.fake5u import FakeFiveU
from app.forwarder import Forwarder


class Sync(Forwarder):
    """Runs jobs inline so the test is deterministic."""
    def submit(self, key, fn, *args):
        if key in ("portal", "board"):
            return
        fn(*args)

    def wait_step(self):  # what the other threads do in production: read the carriers' replies
        msgs, _ = self.api.poll(int(store.kv_get("since_id", "0") or 0))
        for m in msgs:
            store.save_mail(m, "in")
        for m in store.unhandled():
            if self.classify(m) == "bid":
                self.handle(m)


def run(f, n=3):
    for _ in range(n):
        f.tick()


def to(api, who):
    return [m for m in api.outbox if m["to"] == who]


def test_deal_quote_book_track():
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("anna@acme.example", "Quote FRA to ORD", "Hi, please quote 320 kg, 1.5 cbm, FRA to ORD, cheapest.")
    run(f)
    quotes = to(api, "anna@acme.example")
    assert len(quotes) == 1 and quotes[0]["in_reply_to"] == rfq["id"]
    deal = store.get(f"deal-{rfq['id']}")
    assert deal["status"] == "quoted"
    totals = sorted(float(o["total"]) for o in deal["data"]["options"].values())
    assert deal["data"]["quote"]["amount"] == f"{totals[0]:.2f} EUR"  # cheapest of portal, sheet and mail bids
    assert deal["data"]["quote"]["amount"] in quotes[0]["body"]
    run(f)
    assert len(to(api, "anna@acme.example")) == 1, "a handled mail is never answered twice"

    api.customer("anna@acme.example", "Re: Quote FRA to ORD", "Great, go ahead and book it.", in_reply_to=quotes[0]["id"])
    run(f)
    booking = store.get(f"booking-{rfq['id']}")
    assert booking and booking["status"] in ("booked", "requested", "confirmed")
    run(f)
    mails = to(api, "anna@acme.example")  # quote, booking under way, then the airline's confirmation passed on
    assert len(mails) == 3 and "Confirmed: BK-MAIL" in mails[-1]["body"]
    session = store.get(f"session-{rfq['id']}")
    assert session["data"]["executions"] == 3 and session["status"] == "idle"

    ref = booking["data"].get("booking_reference") or booking["data"]["team_reference"]
    api.customer("tracking@hackloop.mail", f"Where is {ref}?", f"Hello, where is shipment {ref}?")
    run(f)
    answers = to(api, "tracking@hackloop.mail")
    assert len(answers) == 1 and "Arrives" in answers[0]["body"]


def test_door_to_port_waits_for_truckers():
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("bob@beta.example", "Pickup in 60311", "Pickup at 60311 Frankfurt, 320 kg, 1.5 cbm, FRA to ORD, fastest.")
    run(f, 4)
    deal = store.get(f"deal-{rfq['id']}")
    assert deal["status"] == "quoted"
    assert deal["data"]["quote"]["pickup"]["carrier"] and deal["data"]["request"]["pickup_zone"] == "60"


def test_tariff_mail_replaces_the_airlines_sheet():
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
    assert store.get("tariff-yellowtail-air-freight")["status"] == "active"


def test_restart_mid_turn_keeps_the_session_valid():
    from app import agent
    items = [{"role": "user", "content": "u"},
             {"type": "function_call", "call_id": "a", "name": "crm", "arguments": "{}"},
             {"type": "function_call", "call_id": "b", "name": "crm", "arguments": "{}"},
             {"type": "function_call_output", "call_id": "a", "output": "{}"}]
    agent._close_dangling(items)
    assert [i.get("call_id") for i in items[3:]] == ["a", "b"] and items[-1]["type"] == "function_call_output"
