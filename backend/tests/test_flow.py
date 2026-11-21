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


def test_restart_mid_turn_keeps_the_conversation_valid():
    from app import agent
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {
                "name": "crm", "arguments": "{}"}}, {"id": "b", "type": "function", "function": {
                    "name": "crm", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "a", "content": "{}"}]
    agent._close_dangling(msgs)
    assert [m.get("tool_call_id") for m in msgs[3:]] == ["a", "b"]


# ---- research/pricing: which weight to ask, when to price, which trucker (docs/research/pricing.md) --------

def test_sheetless_airline_is_also_asked_at_the_next_break():
    # Zephyr, Himalaya and Pampero fly to KTM, have no sheet and are not on the portal: their breaks are unknown.
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("carl@gamma.example", "Quote FRA to KTM", "Please quote 280 kg, FRA to KTM, cheapest.")
    run(f)
    assert [m["subject"] for m in to(api, "zephyr-steppe-cargo@hackloop.mail")] == [
        "Rate request FRA-KTM 280 kg", "Rate request FRA-KTM 300 kg"]
    deal = store.get(f"deal-{rfq['id']}")
    assert deal["status"] == "quoted" and deal["data"]["quote"]["amount"] == "1534.40 EUR"  # cheaper of the two


def test_a_sheet_airline_is_asked_once_at_its_cheapest_billed_weight():
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    api.customer("anna@acme.example", "Quote FRA to ORD", "Please quote 240 kg, FRA to ORD, cheapest.")
    run(f)
    assert [m["subject"] for m in to(api, "yellowtail-air-freight@hackloop.mail")] == ["Rate request FRA-ORD 250 kg"]


def test_a_carrier_asked_twice_has_to_answer_twice():
    from app.forwarder import waiting_for
    asked = {"11": "zephyr@x", "12": "zephyr@x", "13": "pampero@x"}
    assert waiting_for({"asked": asked, "replied": ["zephyr@x", "pampero@x"]}) == ["zephyr@x"]
    assert waiting_for({"asked": asked, "replied": ["zephyr@x", "pampero@x", "zephyr@x"]}) == []
    assert waiting_for({}) == []


def test_pickup_rule_decides_which_trucker_the_recommended_option_carries(monkeypatch):
    from dataclasses import replace
    from app import forwarder
    from app.pricing import Offer
    from decimal import Decimal as D
    f = Sync(FakeFiveU())
    air = [Offer("air", "Slow", D(700), D(5), "sheet"), Offer("air", "Fast", D(900), D(2), "sheet")]
    # live trucker bids, zone 60 -> FRA, Sat 21 Nov 14:10 UTC (mails 164-168)
    trucks = [Offer("pickup", n, D(p), (D(h) / 24).quantize(D("0.001")), "email") for n, p, h in [
        ("Bodenseefracht", "88.60", 26), ("Westfalenroute", "96.80", 23), ("Isarwelle Spedition", "129.80", 16),
        ("Domblick Kurierdienst", "151.60", 15), ("Taunusfracht", "177.40", 3)]]
    req = {"origin": "FRA", "destination": "ORD", "weight_kg": "320", "volume_cbm": None, "chargeable_kg": "320",
           "pieces": 1, "pickup_zone": "60", "pickup_postcode": "60311"}
    store.put("deal-1", "deal", "pricing", {"root": 1, "request": req, "offers": [o.as_dict() for o in air + trucks]})

    base = forwarder.settings

    def recommended(preference, **rules):
        monkeypatch.setattr(forwarder, "settings", replace(base, **rules))
        out = f.options("deal-1", preference)
        row = next(o for o in out["options"] if o["option"] == out["recommended"])
        return row["airline"], row["pickup"]["trucker"], row["total"]

    # default (behaviour so far): the trucker follows the customer's preference
    assert recommended("cheapest") == ("Slow", "Bodenseefracht", "788.60 EUR")
    assert recommended("fastest") == ("Fast", "Taunusfracht", "1077.40 EUR")
    # the fastest trucker is 88.80 EUR more: 9 % on this shipment, outside the 5 % band if 5U expects another
    assert recommended("fastest", pickup_rule="cheapest") == ("Fast", "Bodenseefracht", "988.60 EUR")
    assert recommended("fastest", pickup_rule="balanced", balance_rule="minmax") == ("Fast", "Westfalenroute", "996.80 EUR")
    assert recommended("cheapest", pickup_rule="balanced", balance_rule="minmax") == ("Slow", "Westfalenroute", "796.80 EUR")
    # a request without a stated preference
    assert recommended("unspecified", pickup_rule="cheapest", unspecified_rule="cheapest")[0] == "Slow"
    assert recommended("unspecified", pickup_rule="cheapest")[0] == "Fast"  # default: ratio balance, speed dominates
