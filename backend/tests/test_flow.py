"""The forwarder agent against the fake 5U, driven by a scripted model: quote -> accept -> book -> track."""
import json
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
    # live 5U airlines answer status questions with their quote form: the answer comes from our record
    assert len(answers) == 1 and "Our estimate:" in answers[0]["body"]
    assert "carrier_status" not in store.get(f"booking-{rfq['id']}")["data"]


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
    assert [r["data"]["airline"] for r in store.records("tariff", "active")] == ["Yellowtail Air Freight"]


def test_restart_mid_turn_keeps_the_session_valid():
    from app import agent
    items = [{"role": "user", "content": "u"},
             {"type": "function_call", "call_id": "a", "name": "crm", "arguments": "{}"},
             {"type": "function_call", "call_id": "b", "name": "crm", "arguments": "{}"},
             {"type": "function_call_output", "call_id": "a", "output": "{}"}]
    agent._close_dangling(items)
    assert [i.get("call_id") for i in items[3:]] == ["a", "b"] and items[-1]["type"] == "function_call_output"


# ---- research/pricing: which weight to ask, when to price, which trucker (docs/challenges/5u-facts.md) ---

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

    # `asked`: the trucker follows the customer's preference
    assert recommended("cheapest", pickup_rule="asked") == ("Slow", "Bodenseefracht", "788.60 EUR")
    assert recommended("fastest", pickup_rule="asked") == ("Fast", "Taunusfracht", "1077.40 EUR")
    # the fastest trucker is 88.80 EUR more: 9 % on this shipment, outside the 5 % band if 5U expects another
    assert recommended("fastest", pickup_rule="cheapest") == ("Fast", "Bodenseefracht", "988.60 EUR")
    assert recommended("fastest", pickup_rule="balanced", balance_rule="minmax") == ("Fast", "Westfalenroute", "996.80 EUR")
    assert recommended("cheapest", pickup_rule="balanced", balance_rule="minmax") == ("Slow", "Westfalenroute", "796.80 EUR")
    # a request without a stated preference
    assert recommended("unspecified", pickup_rule="cheapest", unspecified_rule="cheapest")[0] == "Slow"
    assert recommended("unspecified", pickup_rule="cheapest")[0] == "Fast"  # default: ratio balance, speed dominates


# ---- research: tracking needs the airline's word (5U at the booth, docs/news.md) ---------------------------------

def test_a_tracking_session_can_ask_the_airline_and_wait_for_its_status():
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    ctx = tools.Ctx(f, "session-900", "deal-900", 900, "tracking", None)   # a tracking thread: nothing to price
    assert "error" in tools.get_offers(ctx, None, "unspecified", 1)        # nobody asked yet: nothing to wait for
    tools.mail_carrier(ctx, "yellowtail-air-freight@hackloop.mail", "Status of booking BK-1",
                       "Hello, where is the shipment under booking BK-1 (FRA-ORD) now?", None)
    out = tools.get_offers(ctx, None, "unspecified", 5)
    # live 5U airlines answer with their quote form; the waiting path still brings the answer back
    assert out["still_waiting_for"] == [] and "To quote we need" in out["carrier_messages"][0]["text"]
    assert store.get("deal-900")["status"] == "new"                         # not shown as a deal being priced


def test_crm_gives_the_airlines_address_for_a_status_question():
    from app import tools
    f = Sync(FakeFiveU())
    booking = {"booking_reference": "BK-7", "team_reference": "SM-5", "airline": "Yellowtail Air Freight",
               "route": "FRA-ORD", "transit_days": "4", "status": "confirmed", "booked_at": 1795273200.0}
    store.put("deal-5", "deal", "booked", {"root": 5, "customer": "anna@acme.example", "booking": booking})
    store.put("booking-5", "booking", "confirmed", booking)
    out = tools.crm(tools.Ctx(f, "session-9", "deal-9", 9, "tracking", None), "BK-7")
    assert out["matches"][0]["booking"]["airline_email"] == "yellowtail-air-freight@hackloop.mail"


def test_a_carrier_that_says_no_takes_its_sheet_price_with_it():
    from decimal import Decimal as D
    from app.pricing import Offer
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    req = {"origin": "FRA", "destination": "BKK", "weight_kg": "260", "volume_cbm": "1.300", "chargeable_kg": "260",
           "pieces": 1, "pickup_zone": None, "pickup_postcode": None}
    sheet = [Offer("air", "Yellowtail Air Freight", D("930.80"), D(2), "sheet"),
             Offer("air", "Orion Cargo Air", D("990.00"), D(3), "sheet")]
    yl = "yellowtail-air-freight@hackloop.mail"
    store.put("deal-1", "deal", "pricing", {"root": 1, "request": req, "offers": [o.as_dict() for o in sheet],
                                             "asked": {"7": yl}, "replied": []})
    store.kv_set("bidreq:7", "deal-1")
    assert [o["airline"] for o in f.options("deal-1", "fastest")["options"]] == ["Yellowtail Air Freight", "Orion Cargo Air"]
    api._deliver(yl, api.mailbox, "Re: Rate request FRA-BKK 260 kg",
                 "Hello, we do not serve this lane now: all flights to Bangkok are suspended (tsunami warning).", 7)
    run(f)
    out = f.options("deal-1", "fastest")
    assert [o["airline"] for o in out["options"]] == ["Orion Cargo Air"] and out["recommended"] == "A1"
    assert "suspended" in out["carriers_without_price"][0]["says"] and out["still_waiting_for"] == []


def test_a_city_is_its_airport_and_a_signature_is_no_pickup():
    from app.forwarder import normalise
    kg = {"value": 650, "unit": "kg", "per_piece": False}
    ship = {"origin_airport": "CGN", "pickup": None, "destination_airport": "Lagos, Nigeria", "pieces": 6,
            "weight": kg, "volume": None, "dimensions": [], "cargo": {"commodity": None, "ready_date": None, "notes": None}}
    r = normalise(ship, kit.world())
    assert r["destination"] == "LOS" and not r["missing"] and r["pickup_zone"] is None
    assert normalise({**ship, "destination_airport": "Peking"}, kit.world())["destination"] == "PEK"
    assert normalise({**ship, "destination_airport": "pek"}, kit.world())["destination"] == "PEK"
    hint = normalise({**ship, "destination_airport": None}, kit.world())["missing"][0]
    assert "LOS Lagos" in hint and "PEK Beijing" in hint


def test_a_quote_with_two_amounts_is_sent_and_flagged():
    """No gate on the model's text (the prompt teaches one total); the diagnostics flag it for the team."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("sam@lumen.example", "Quote", "1200 kg MUC to LAX, cheapest and fastest please")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    opt = {"air": {"carrier": "Yellowtail Air Freight"}, "pickup": None, "total": "2748.00", "total_text": "2748.00 EUR"}
    store.put(ctx.deal_id, "deal", "pricing", {"root": rfq["id"], "received_at": None, "options": {"A1": opt}})
    two = "Hi Sam,\n\nCheapest: 2748.00 EUR all-in\nFastest: 3336.00 EUR all-in\n\nGiulia"
    out = tools.send_mail(ctx, "quote", two, "A1", None)
    assert out["recorded_quote"] == "2748.00 EUR" and len(to(api, "sam@lumen.example")) == 1
    assert any("quote mail amounts" in e["summary"] for e in store.events() if e["kind"] == "error")


def test_a_december_tariff_does_not_reprice_november():
    from app import kit
    kit.load(FakeFiveU())
    nov = [l for l in kit.world().sheet("FRA", "ORD", on="2026-11-25") if l["airline"] == "Yellowtail Air Freight"][0]
    dec = {**nov, "rates_eur_per_kg": [str(round(float(r) * 1.2, 2)) for r in nov["rates_eur_per_kg"]]}
    kit.add_sheet("Yellowtail Air Freight", [dec], "test", "2026-12-01", "2026-12-31")
    on_nov = [l for l in kit.world().sheet("FRA", "ORD", on="2026-11-25") if l["airline"] == "Yellowtail Air Freight"]
    on_dec = [l for l in kit.world().sheet("FRA", "ORD", on="2026-12-03") if l["airline"] == "Yellowtail Air Freight"]
    assert on_nov[0]["rates_eur_per_kg"] == nov["rates_eur_per_kg"]
    assert on_dec[0]["rates_eur_per_kg"] == dec["rates_eur_per_kg"]


def test_a_bid_quoted_per_kg_gets_its_total_from_code():
    from app.forwarder import Forwarder
    f = Forwarder(FakeFiveU())
    store.kv_set("bidweight:41", "300")
    o = {"carrier": "x", "available": True, "total": None, "currency": "EUR", "fx_eur_per_unit": None,
         "rate_per_kg": 2.42, "minimum_charge": 110, "surcharges_per_kg": 0.77, "fixed_fees": 25, "billed_kg": None,
         "time_value": 4, "time_unit": "days", "reference": "R-9", "valid_until": None, "note": None}
    m = {"id": 42, "in_reply_to": 41, "sender": "yellowtail-air-freight@hackloop.mail"}
    off = f.offer(o, m, kit.world().carrier_by_email(m["sender"]))
    assert str(off.total) == "982.00"  # 300 x 2.42 + 300 x 0.77 + 25


def test_the_server_asks_for_the_team_password(monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main, "_PASSWORD", "s3cret")
    c = TestClient(main.app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/deals").status_code == 401
    ok = {"Authorization": "Basic " + base64.b64encode(b"team:s3cret").decode()}
    assert c.get("/api/deals", headers=ok).status_code == 200


def test_no_options_says_why_with_what_the_carriers_wrote():
    """Live round 15: the truckers asked for the postcode, the bid reader called it a no, and get_offers returned an
    empty list with nothing else; the agent told the customer no airline flew the route. Empty now says why."""
    from decimal import Decimal as D
    from app.pricing import Offer
    f = Sync(FakeFiveU())
    req = {"origin": "MUC", "destination": "SGN", "weight_kg": "572", "volume_cbm": "2.290", "chargeable_kg": "572",
           "pieces": 11, "pickup_zone": "93", "pickup_postcode": None}
    asks = "Hello,\n\nthank you for your request. To quote we need:\n- the pickup postcode\n"
    store.put("deal-1", "deal", "pricing", {
        "root": 1, "request": req, "offers": [Offer("air", "Helix Air Freight", D("2316.60"), D(5), "email").as_dict()],
        "carrier_messages": [{"from": "isarwelle-spedition@hackloop.mail", "mail": 3793, "text": asks,
                              "declined": True, "had_sheet_price": False}]})
    out = f.options("deal-1", "cheapest")
    assert out["options"] == [] and out["no_options_because"] == "no trucker has priced the pickup"
    assert "pickup postcode" in out["carriers_without_price"][0]["says"]


def test_a_town_without_postcode_asks_the_truckers_with_its_postcode():
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    req = {"origin": "MUC", "destination": "RUH", "weight_kg": "970", "volume_cbm": "9.060", "chargeable_kg": "1513",
           "pieces": 7, "pickup_zone": "86", "pickup_postcode": None, "ready_date": "2026-11-27"}
    store.put("deal-1", "deal", "pricing", {"root": 1, "request": req})
    trucker = next(c for c in kit.world().carriers if c.kind == "trucker" and "86" in c.serves)
    f.ask_trucker("deal-1", trucker, req)
    assert "86150 Augsburg" in api.outbox[-1]["body"]


def test_a_misread_bid_amount_is_read_again(monkeypatch):
    """Live Sat 18:27: '94.08 EUR' came back from the bid reader as 9408 and sat in the options."""
    from app import language
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    req = {"origin": "STR", "destination": "EZE", "weight_kg": "544", "volume_cbm": "1.860", "chargeable_kg": "544",
           "pieces": 11, "pickup_zone": "70", "pickup_postcode": "70498"}
    store.put("deal-1", "deal", "pricing", {"root": 1, "request": req, "asked": {"9": "rheinufer-spedition@hackloop.mail"}})
    store.kv_set("bidreq:9", "deal-1")
    reads = iter([[{"available": True, "total": 9408, "currency": "EUR", "time_value": 28, "time_unit": "hours"}],
                  [{"available": True, "total": 94.08, "currency": "EUR", "time_value": 28, "time_unit": "hours"}]])
    monkeypatch.setattr(language, "read_bid", lambda *a: next(reads))
    api._deliver("rheinufer-spedition@hackloop.mail", api.mailbox, "Re: Pickup quote zone 70 to STR",
                 "Our total price for pickup in Stuttgart and delivery to STR Airport is 94.08 EUR. Pickup time: 28 hours", 9)
    run(f)
    offers = store.get("deal-1")["data"]["offers"]
    assert [o["total"] for o in offers] == ["94.08"]


def test_portal_down_asks_its_airlines_by_mail_also_at_the_break(monkeypatch):
    """Live Sat 18:38: the rate API answers 503. The portal airlines are asked by mail, like every mail airline also
    at the break above, where billing can be cheaper (299 kg cost more than 300 kg on the portal)."""
    api = FakeFiveU()
    kit.load(api)
    monkeypatch.setattr(api, "rate", lambda *a, **k: {"error": True, "status": 503, "detail": "The rate API is unavailable."})
    monkeypatch.setattr(api, "brackets", lambda *a, **k: None)
    kit.world().brackets.clear()
    f = Sync(api)
    lane = next((o, d) for (o, d), airlines in kit.world().portal.items() if airlines)
    name = kit.world().portal[lane][0]["name"]
    email = kit.world().carrier_by_name(name).email
    api.customer("dora@delta.example", f"Quote {lane[0]} to {lane[1]}", f"Please quote 280 kg, {lane[0]} to {lane[1]}, cheapest.")
    run(f)
    subjects = [m["subject"] for m in to(api, email)]
    assert f"Rate request {lane[0]}-{lane[1]} 280 kg" in subjects and f"Rate request {lane[0]}-{lane[1]} 300 kg" in subjects


def test_done_closes_the_turn_without_another_model_call():
    """The model marks the reply done: the turn ends there (a closing message is one more paid call)."""
    from app import llm
    from tests.conftest import call
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    calls = []

    def agent_turn(items, tools):
        calls.append(len(items))
        return call("no_reply", reason="only a thank-you", done=True)
    llm.use_fake_turn(agent_turn)
    api.customer("anna@acme.example", "Thanks", "Thanks for your help!")
    run(f)
    assert len(calls) == 1


def test_an_airline_that_told_us_its_lanes_is_not_asked_for_another_lane():
    """Live: 28 of 74 bid readings in an hour were 'we do not serve this lane'. A carrier's own list of lanes is
    kept for two hours; the agent still sees who was not asked and can ask with mail_carrier."""
    import json as _json, time as _time
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    w = kit.world()
    lane, airline = next(((o, d), c) for c in w.carriers if c.kind == "airline"
                         for (o, d) in [(l["origin"], l["destination"]) for l in w.sheet_lanes if l["airline"] == c.name]
                         if c in w.email_airlines(o, d))
    store.kv_set(f"lanes:{airline.email}", _json.dumps({"lanes": ["XXX-YYY"], "at": _time.time()}))
    req = {"origin": lane[0], "destination": lane[1], "weight_kg": "300", "volume_cbm": None, "chargeable_kg": "300",
           "pieces": 1, "pickup_zone": None, "pickup_postcode": None, "ready_date": None}
    store.put("deal-1", "deal", "pricing", {"root": 1, "request": req})
    f._ask_everyone("deal-1", req)
    assert not [m for m in api.outbox if m["to"] == airline.email]
    assert f.options("deal-1", "cheapest")["not_asked"][0]["carrier"] == airline.name


def test_a_confirmation_that_matches_the_booking_does_not_wake_the_session():
    from app.forwarder import confirmation_matches
    b = {"booking_reference": "BK-ZB4HK7UW", "via": "portal", "amount": "1594.80 EUR", "pickup": {"total": "186.80"}}
    mail = "Booking BK-ZB4HK7UW confirmed\nBooking reference: BK-ZB4HK7UW\nPrice: 1408.00 EUR\nStatus: booked"
    assert confirmation_matches(b, mail)
    assert not confirmation_matches(b, mail.replace("1408.00", "1452.00"))  # another price: the agent reads it
    assert not confirmation_matches({**b, "via": "mail"}, mail)


def test_airline_news_after_the_booking_reaches_the_deal():
    """A delay or a change the airline mails after the booking was dropped as 'other': tracking would have answered
    from an old record. Now it goes on the booking (crm and tracking read it) and wakes the deal's session."""
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    b = {"team_reference": "SM-77", "deal": "deal-77", "customer": "anna@acme.example", "airline": "Meridian Freightways",
         "route": "STR-MNL", "transit_days": "3", "booking_reference": "BK-ZB4HK7UW", "via": "portal",
         "amount": "1594.80 EUR", "status": "confirmed"}
    store.put("booking-77", "booking", "confirmed", b)
    store.put("deal-77", "deal", "booked", {"root": 77, "booking": b})
    store.put("session-77", "session", "idle", {"root": 77, "task": "customer", "seen": [], "executions": 1, "items": []})
    api._deliver("meridian-freightways@hackloop.mail", api.mailbox, "Schedule change BK-ZB4HK7UW",
                 "Hello,\n\nflight for booking BK-ZB4HK7UW is delayed by 24 hours: new departure 28 Nov.\n\nMeridian", None)
    run(f)
    assert "delayed by 24 hours" in store.get("booking-77")["data"]["carrier_status"]["text"]
    assert store.get("booking-77")["data"]["status"] == "confirmed"  # news, not a new confirmation
    assert "delayed by 24 hours" in json.dumps(store.get("session-77")["data"]["items"])  # the session heard it


def test_a_customer_thread_sees_only_that_customers_deals():
    from app import tools
    store.put("deal-1", "deal", "booked", {"root": 1, "customer": "anna@acme.example", "subject": "FRA-ORD"})
    store.put("deal-2", "deal", "booked", {"root": 2, "customer": "rival@other.example", "subject": "FRA-ORD"})
    ctx = tools.Ctx(None, "session-1", "deal-1", 1, "customer", None)
    assert [m["deal_id"] for m in tools.crm(ctx, "FRA-ORD")["matches"]] == ["deal-1"]
    assert "error" in tools.deal(ctx, "deal-2")
    tracking = tools.Ctx(None, "session-9", "deal-9", 9, "tracking", None)
    assert len(tools.crm(tracking, "FRA-ORD")["matches"]) == 2  # the tracking desk asks for any customer


def test_a_new_thread_starts_with_the_customers_earlier_notes():
    """Round 42: 'do not offer Zephyr Steppe Cargo for this shipment or any of our future inquiries'. The next
    request is a new thread and a new session: it starts with what we noted in that customer's earlier deals."""
    from app import agent
    store.put("deal-5", "deal", "quoted", {"root": 5, "customer": "petra@meyer.example", "subject": "Quote to ULN",
              "notes": [{"at": 1.0, "text": "Customer refuses Zephyr Steppe Cargo, also for future inquiries", "flag": "none"}]})
    store.put("deal-6", "deal", "quoted", {"root": 6, "customer": "other@x.example", "subject": "Quote to JFK",
              "notes": [{"at": 2.0, "text": "someone else's note", "flag": "none"}]})
    text = agent._customer_notes(9, {"sender": "petra@meyer.example"})
    assert "Zephyr" in text and "someone else" not in text
    assert agent._customer_notes(9, {"sender": "new@customer.example"}) == ""


def test_a_booking_at_another_price_says_so_and_its_confirmation_stays_quiet():
    """Round 48: quoted 5655.55, the portal booked the same rate at 6221.11. `book` returned both numbers without
    saying they differ, so the agent confirmed without the price and corrected itself after the airline's mail."""
    from app.forwarder import confirmation_matches
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("anna@acme.example", "Quote FRA to ORD", "Hi, please quote 320 kg, 1.5 cbm, FRA to ORD, cheapest.")
    run(f)
    deal_id = f"deal-{rfq['id']}"
    opts = store.get(deal_id)["data"]["options"]
    oid, opt = next((k, o) for k, o in opts.items() if o["air"]["source"] == "portal")
    rate = api.rates[opt["air"]["rate_id"]]
    rate["total"] = f"{float(rate['total']) * 1.1:.2f}"  # the airline books at 10 % more than it quoted
    b = f.book_option(deal_id, oid)
    assert b["price_changed"] == {"quoted": opt["total_text"], "booked": f"{rate['total']} EUR"}
    assert b["amount"] == f"{rate['total']} EUR" and b["quoted_amount"] == opt["total_text"]
    mail = f"Booking {b['booking_reference']} confirmed\nBooking reference: {b['booking_reference']}\n" \
           f"Price: {rate['total']} EUR\nStatus: booked"
    assert confirmation_matches(b, mail)  # it confirms what the booking already told the agent: not news

    rate["total"] = opt["air"]["total"]
    same = f.book_option(deal_id, oid)
    assert "price_changed" not in same and same["amount"] == opt["total_text"]


def test_a_mailbox_poll_is_never_retried_sooner_than_5us_limit():
    """5U allows one poll per 5 seconds per key. The generic retry (0.5 s after a 502 or a dropped connection) made
    a second poll inside the limit: a 429 of our own making. A failed poll is simply the next tick's poll."""
    import httpx
    from app.fiveu import FiveU
    calls, answers = [], iter([httpx.Response(502), httpx.Response(429, json={"detail": "one poll per 5 seconds"}),
                               httpx.Response(200, json={"messages": [{"id": 7}], "next_since_id": 8})])

    def handler(request):
        calls.append(request.url.path)
        return next(answers)
    api = FiveU("http://5u.test", "k")
    api.http = httpx.Client(base_url="http://5u.test", transport=httpx.MockTransport(handler))
    api._last_poll = 0
    assert api.poll(3) == ([], 3) and len(calls) == 1  # 502: no retry inside the limit
    assert api.poll(3) == ([], 3) and len(calls) == 1  # too soon: no request at all
    api._last_poll = 0
    assert api.poll(3) == ([], 3) and api.poll_gap == 5.5  # 429 'per 5 seconds': the gap stays 5.5 s
    api._last_poll = 0
    assert api.poll(3) == ([{"id": 7}], 8) and len(calls) == 3


def _booked_by_mail(api):
    """Round 51: door-to-port booked by mail with the airline (portal booking unavailable for that airline)."""
    b = {"team_reference": "SM-81", "deal": "deal-81", "customer": "jonas@kessler.example", "airline": "Nova Atlas Cargo",
         "route": "MUC-BKK", "transit_days": "2", "via": "email", "status": "requested", "rate_id": "R-vuCFXpwNvy1h_5sL",
         "amount": "4659.12 EUR", "pickup": {"total": "192.60"}}
    ask = api._deliver("start-milan@hackloop.mail", "nova-atlas-cargo@hackloop.mail", "Booking R-vuCFXpwNvy1h_5sL",
                       "we would like to book your offer R-vuCFXpwNvy1h_5sL")
    store.kv_set(f"bidreq:{ask['id']}", "deal-81")
    b["request_mail"] = ask["id"]
    store.put("booking-81", "booking", "requested", b)
    store.put("deal-81", "deal", "booked", {"root": 81, "booking": b})
    store.put("session-81", "session", "idle", {"root": 81, "task": "customer", "seen": [], "executions": 1, "items": []})
    return ask


def test_an_airline_confirmation_is_read_against_the_flight_price_we_booked():
    """Round 51: the airline confirmed 4466.52 for the flight; the agent compared it with the 4659.12 all-in (pickup
    192.60 included) and told the customer the price had changed. Code now says what the price means."""
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    ask = _booked_by_mail(api)
    reply = api._deliver("nova-atlas-cargo@hackloop.mail", api.mailbox, "Re: Booking R-vuCFXpwNvy1h_5sL",
                         "Hello,\n\nthank you for your booking.\n\nBooking reference: BK-44RD0LQJ\nRate reference: "
                         "R-vuCFXpwNvy1h_5sL\nLane: MUC-BKK, 923 kg\nPrice: 4466.52 EUR\nStatus: booked\n", ask["id"])
    run(f)
    assert store.get("deal-81")["data"].get("offers", []) == []  # a booking reply is not an offer
    told = json.dumps(store.get("session-81")["data"]["items"])
    assert "is the flight price we booked" in told and "stays 4659.12 EUR" in told
    api._deliver("nova-atlas-cargo@hackloop.mail", api.mailbox, "Booking BK-44RD0LQJ confirmed",
                 "Hello,\n\nyour booking BK-44RD0LQJ is confirmed.\n\nBooking reference: BK-44RD0LQJ\nYour reference: "
                 "SM-81\nPrice: 4913.17 EUR\nStatus: booked and ready to ship\n")
    run(f)
    b = store.get("booking-81")["data"]
    assert b["status"] == "confirmed" and b["amount"] == "5105.77 EUR"  # 4913.17 for the flight + 192.60 pickup
    assert b["price_changed"] == {"quoted": "4659.12 EUR", "booked": "5105.77 EUR"}
    assert "all-in total is now 5105.77 EUR" in json.dumps(store.get("session-81")["data"]["items"])
    assert reply["id"]


def test_only_a_carrier_on_our_list_can_confirm_or_reprice_a_booking():
    """The router goes by who sent a mail, never by what it claims. A 'Booking BK-... confirmed' subject from an
    address that only looks like an airline's, with our real reference and another price, would have repriced the
    booking and the customer's total. From a carrier on the list it is a confirmation; from anyone else, a mail the
    agent reads like any other."""
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    _booked_by_mail(api)
    body = "your booking BK-44RD0LQJ is confirmed.\nYour reference: SM-81\nPrice: 9999.00 EUR\nStatus: booked\n"
    fake = {"id": 99901, "sender": "nova-atlas-carg0@hackloop.mail", "subject": "Booking BK-44RD0LQJ confirmed",
            "body": body, "in_reply_to": None, "root": 99901}
    assert f.classify(fake) == "customer"
    real = {**fake, "sender": "nova-atlas-cargo@hackloop.mail"}
    assert kit.world().carrier_by_email(real["sender"]) and f.classify(real) == "booking"


def test_a_reference_read_with_words_around_it_is_kept_as_its_id():
    from app.forwarder import clean_reference
    assert clean_reference("R-IR61CclGsFVVd1un when booking.") == "R-IR61CclGsFVVd1un"
    assert clean_reference("R--Bhl2SbrPA2LipP9") == "R--Bhl2SbrPA2LipP9"  # a valid id is kept as written
    assert clean_reference("TRK-5150") == "TRK-5150" and clean_reference("Q-2026/11/0034") == "Q-2026/11/0034"
    assert clean_reference(None) is None


def test_a_carrier_price_in_an_attachment_is_read():
    """Round 63: the truckers answered 'You find our price offer in the attachment' (PDF, Word, a voice message).
    The bid reader saw only the body, found no price, and the round had no pickup and no quote."""
    from app import docs
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    files = {1: b"Price offer TRK-5779\nTotal: 165.70 EUR\nPickup time: 9 hours", 2: bytes(range(256)) * 50}
    api.attachment = lambda mid, aid: files[aid]
    m = {"id": 5, "sender": "elbkante-logistik@hackloop.mail", "subject": "Re: Pickup", "body": "See the attachment.",
         "attachments": [{"id": 1, "filename": "price-offer.txt"}, {"id": 2, "filename": "voice-message.mp3"}]}
    body = f.with_attachments(m)["body"]
    assert "Total: 165.70 EUR" in body and "[voice message voice-message.mp3, transcribed]" in body
    assert docs.text("blob.bin", bytes(range(256)) * 50).startswith("[binary attachment")
    assert f.with_attachments({**m, "attachments": []}) == {**m, "attachments": []}


def test_the_ready_date_is_a_date_however_it_was_written():
    """Round 65: 'ready on 24 November 2026' reached the schedule as text; it fell back to today and the quote
    said the departure was before the ready date."""
    from app.forwarder import normalise
    kit.load(FakeFiveU())
    s = {"origin_airport": "FRA", "destination_airport": "ORD", "lots": [{"pieces": 1, "weight": {"value": 100, "unit": "kg"}}]}
    for written in ("24 November 2026", "2026-11-24", "24.11.2026", "Nov 24, 2026"):
        assert normalise({**s, "cargo": {"ready_date": written}}, kit.world())["ready_date"] == "2026-11-24"


def test_any_attachment_becomes_what_a_person_would_read():
    """5U sends files in more and more forms (round 63: offers as PDF, Word and a voice message; round 65: the
    request itself as a voice message). One reader turns each into text, or says why it cannot."""
    import io, zipfile
    from email.message import EmailMessage
    from app import docs
    from app.forwarder import amounts_in
    from decimal import Decimal
    assert docs.text("voice-message.mp3", b"ID3...").startswith("[voice message voice-message.mp3, transcribed]")
    assert docs.text("scan.JPG", b"\xff\xd8...").startswith("[picture scan.JPG, as read]")
    assert docs.text("offer.txt", "Total: 340,60 €".encode("utf-16")) == "Total: 340,60 €"
    assert docs.text("offer.csv", "Gewicht;Preis\n1.410;340,60 €".encode("cp1252")).endswith("340,60 €")
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("offer.txt", "Total: 165.70 EUR")
        f.writestr("photo.png", b"\x89PNG...")
    out = docs.text("documents.zip", z.getvalue())
    assert "Total: 165.70 EUR" in out and "[picture photo.png, as read]" in out
    msg = EmailMessage()
    msg["From"], msg["Subject"] = "shipper@example.com", "Packing list"
    msg.set_content("See the list attached.")
    msg.add_attachment(b"3 pallets, 212 kg each", maintype="text", subtype="plain", filename="list.txt")
    out = docs.text("forwarded.eml", bytes(msg))
    assert "Packing list" in out and "3 pallets, 212 kg each" in out
    assert Decimal("340.60") in amounts_in("the total is 340 euros and 60 cents")


def test_units_are_read_however_written_and_never_guessed():
    """'2 metric tons' read as 2 kg, or '45 cubic feet' as 45 cbm, prices a shipment 1000 or 35 times wrong."""
    from app import language
    from app.forwarder import normalise
    from decimal import Decimal
    assert language.weight_kg({"value": 2, "unit": "Metric Tons"}, 1) == 2000
    assert language.weight_kg({"value": 100, "unit": "LBS."}, 1) == Decimal("45.359237")
    assert round(language.volume_cbm({"value": 45, "unit": "cubic feet"}, [], 1), 3) == Decimal("1.274")
    assert language.volume_cbm({}, [{"length": 48, "width": 40, "height": 50, "unit": "Inches", "count": 1}], 1) > 1
    kit.load(FakeFiveU())
    s = {"origin_airport": "FRA", "destination_airport": "ORD",
         "lots": [{"pieces": 1, "weight": {"value": 3, "unit": "stone"}, "volume": {"value": 1, "unit": "cbm"}}]}
    n = normalise(s, kit.world())
    assert n["weight_kg"] is None and "weight unit 'stone'" in " ".join(n["missing"])


def test_a_truckers_time_is_read_by_code_when_the_reader_misses_it():
    from app import language
    from decimal import Decimal
    assert language.days(28, "hours from order to collection") == Decimal("1.167")
    assert language.days(28, "parsecs") is None and language.days(4, None) == 4
    assert language.days(3, "business days") == 3
    assert language.time_in("Lead time           28 hours from order to collection") == Decimal("1.167")
    assert language.time_in("Our driver can be at the pickup address 13 hours after your order.") == Decimal("0.542")
    assert language.time_in("We need 12 hours from your order to the collection.") == Decimal("0.5")
    assert language.time_in("Collection in 7 hours") == Decimal("0.292")
    assert language.time_in("waiting time after the first 30 minutes, 45.00 EUR for each hour") is None


def test_the_language_of_a_mail_and_times_said_in_words():
    from app import language
    from decimal import Decimal
    en = ("Hello, I am on the road today, so I recorded our quotation request as a voice message. Please listen to "
          "the attached recording. Please reply by mail with your all-in price in EUR.\\n\\nBest greetings from "
          "Regensburg\\nTobias Auer\\nVersand / Shipping\\nAuer Maschinenbau GmbH")
    de = "Guten Tag, bitte senden Sie uns ein Angebot für die Sendung. Wir sind ab dem 24. bereit und die Ware ist verpackt."
    assert language.language_of(en) == "English" and language.language_of(de) == "German"
    assert language.language_of("Thanks!\\nViele Gruesse / Many greetings") is None
    assert language.time_in("We need seven hours from your order to the collection.") == Decimal("0.292")
    assert language.time_in("Lead time twenty-four hours from order to collection") == Decimal("1")


def test_a_ready_date_said_relative_to_today_is_the_next_such_day():
    from datetime import date, timedelta
    from app.forwarder import _day
    today = date.today()
    monday = today + timedelta(days=(0 - today.weekday() - 1) % 7 + 1)
    assert _day("Monday") == monday.isoformat() and _day("next Monday") == monday.isoformat()
    assert _day("tomorrow") == (today + timedelta(days=1)).isoformat()
    assert _day("2026-11-24") == "2026-11-24" and _day("whenever") is None


def test_an_offer_asked_as_a_pdf_is_attached_with_the_options_total():
    """Round 76: 'attach your offer as a PDF, our purchasing needs it'. 5U takes attachments on outbound mail; the
    pdf is made by code from the option, so it says what the quote says, one total."""
    import base64
    from app import docs, tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("deniz@rheintal.example", "Air freight quote to DFW", "65 kg from 53345 Bonn to DFW, PDF please")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    opt = {"air": {"carrier": "Lumen Air Cargo", "days": "1", "billed_kg": "65", "total": "279.50"},
           "pickup": {"carrier": "Sternmeile Logistik", "days": "0.458", "total": "129.05"},
           "total": "408.55", "total_text": "408.55 EUR"}
    store.put(ctx.deal_id, "deal", "pricing", {
        "root": rfq["id"], "received_at": None, "customer": "deniz@rheintal.example", "subject": rfq["subject"],
        "request": {"origin": "CGN", "destination": "DFW", "weight_kg": "65", "volume_cbm": "0.370", "pieces": 5,
                    "pickup_postcode": "53345", "ready_date": "2026-11-28", "commodity": "automotive sensors"},
        "options": {"A3": opt}})
    assert "error" in tools.send_mail(ctx, "quote", "x", "A9", None, offer_pdf=True)
    assert not to(api, "deniz@rheintal.example")  # nothing sent without the document asked for
    out = tools.send_mail(ctx, "quote", "Hello Deniz,\n\nTotal: 408.55 EUR all-in\n\nGiulia", "A3", None,
                          offer_pdf=True)
    assert out["recorded_quote"] == "408.55 EUR"
    (mail,) = to(api, "deniz@rheintal.example")
    (att,) = mail["attachments"]
    assert att["filename"].endswith(".pdf") and att["content_type"] == "application/pdf"
    text = docs.text(att["filename"], base64.b64decode(att["content_base64"]))
    assert text.count("408.55 EUR") == 1 and "279.50" not in text and "129.05" not in text
    assert "Lumen Air Cargo" in text and "Sternmeile Logistik" in text and "Sun 29 Nov 2026" in text
    assert "0.37 cbm" in text and "1 day in transit" in text


def test_a_scanned_pdf_page_is_read_and_the_text_pages_are_kept():
    """Sam, Sun 00:10: pypdf needs Pillow for the pictures of a scanned page; without it the whole pdf was lost,
    the text pages too. A pdf of a text page and a scanned page reads as both."""
    import io
    from PIL import Image
    from pypdf import PdfReader, PdfWriter
    from app import docs
    scan = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(scan, "PDF")  # a page that is only a picture
    text = docs.pdf("Offer TRK-1", ["Total for pickup to FRA: 165.70 EUR", "Pickup time: 8 hours"])
    w = PdfWriter()
    for src in (text, scan.getvalue()):
        for p in PdfReader(io.BytesIO(src)).pages:
            w.add_page(p)
    both = io.BytesIO()
    w.write(both)
    out = docs.text("offer.pdf", both.getvalue())
    assert "165.70 EUR" in out and "[page 2, scanned, as read]" in out and "could not read" not in out


def test_a_mail_that_cannot_go_out_does_not_stop_the_price_collection():
    """Sam's F2: a send refused by 5U (its limit, a 5xx) raised out of the collection, and the carriers after it and
    the portal were never asked. Now that one carrier is logged and the rest are asked."""
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    real = api.send
    first = {}

    def refuse_one(to, *a, **k):
        if not first:
            first["to"] = to
            raise RuntimeError("send to x failed: 503")
        return real(to, *a, **k)
    api.send = refuse_one
    rfq = api.customer("ana@ana.example", "Quote", "320 kg, 1.5 cbm, FRA to ORD, cheapest please")
    run(f)
    d = store.get(f"deal-{rfq['id']}")["data"]
    assert first and d.get("asked") and first["to"] not in d["asked"].values()
    assert any(o["source"] == "portal" for o in d["offers"])
    assert any("could not ask" in e["summary"] for e in store.events() if e["kind"] == "error")


def test_an_offer_accepted_in_a_new_thread_is_booked_on_its_own_deal():
    """Probe, Sun 00:30 (real model, fake 5U): "your offer from today is fine, please book it" came as a new mail,
    not a reply. book("A1") found no option on the new thread's deal, the customer got "I will confirm as soon as
    it is secured" and nothing was booked: no booking, no tracking question."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("anna@acme.example", "Quote FRA to ORD", "Hi, please quote 320 kg, 1.5 cbm, FRA to ORD, cheapest.")
    run(f)
    offer = f"deal-{rfq['id']}"
    assert store.get(offer)["data"]["quote"]
    again = api.customer("anna@acme.example", "Your offer for Chicago", "It is fine, please book it.")
    store.save_mail(again, "in")
    ctx = tools.Ctx(f, f"session-{again['id']}", f"deal-{again['id']}", again["id"], "customer", store.mail(again["id"]))
    miss = tools.book(ctx, "A1")
    assert "unknown option" in miss["error"] and "deal_id" in miss["hint"]
    booked = tools.book(ctx, "A1", offer)
    assert booked["status"] in ("booked", "requested") and booked["deal"] == offer
    assert store.get(offer)["status"] == "booked" and store.get(f"booking-{rfq['id']}")
    # the tracking desk sees every deal and may book none
    desk = tools.Ctx(f, "session-900", "deal-900", 900, "tracking", None)
    assert tools.book(desk, "A1", offer) == {"error": "that deal belongs to another customer"}
    other = api.customer("eve@other.example", "Hello", "Please book option A1 of that deal.")
    store.save_mail(other, "in")
    eve = tools.Ctx(f, f"session-{other['id']}", f"deal-{other['id']}", other["id"], "customer", store.mail(other["id"]))
    assert tools.book(eve, "A1", offer) == {"error": "that deal belongs to another customer"}


def test_an_xls_is_read_like_an_xlsx():
    """`.xls` is on 5U's own list of attachment types and was the one we passed on as a binary (Sam, Sun 00:33)."""
    from pathlib import Path
    from app import docs
    xls = docs.text("Packing-List.XLS", (Path(__file__).parent / "data" / "packing-list.xls").read_bytes())
    assert "# sheet Packing list" in xls and "2\t120\t80\t95\t160.5" in xls and "Total gross weight kg\t356" in xls
    assert "Ready for collection\t2026-11-24" in xls                              # a date cell, not its serial 46350
    assert docs.text("export.xls", b"Weight kg\t320\nPickup\t24.11.2026") == "Weight kg\t320\nPickup\t24.11.2026"


def test_an_airlines_answer_to_our_own_mail_after_the_booking_is_news():
    """Sam's probe, Sun 00:30: the agent asked the airline to cancel a booking; the airline's "booking cancelled" was
    read as a bid, woke nobody, and tracking later said the shipment should be in transit."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    b = {"team_reference": "SM-78", "deal": "deal-78", "customer": "anna@acme.example", "airline": "Meridian Freightways",
         "route": "STR-MNL", "transit_days": "3", "booking_reference": "BK-ZB4HK7UX", "via": "portal",
         "amount": "1594.80 EUR", "status": "confirmed"}
    store.put("booking-78", "booking", "confirmed", b)
    store.put("deal-78", "deal", "booked", {"root": 78, "booking": b, "asked": {}})
    store.put("session-78", "session", "idle", {"root": 78, "task": "customer", "seen": [], "executions": 1, "items": []})
    ctx = tools.Ctx(f, "session-78", "deal-78", 78, "customer", None)
    out = tools.mail_carrier(ctx, "meridian-freightways@hackloop.mail", "Cancel BK-ZB4HK7UX",
                             "Please cancel booking BK-ZB4HK7UX.", None)
    assert "booked" in out["note"]
    api._deliver("meridian-freightways@hackloop.mail", api.mailbox, "Re: Cancel BK-ZB4HK7UX",
                 "Hello,\n\nbooking BK-ZB4HK7UX has been cancelled.\n\nMeridian", out["sent"])
    run(f)
    assert "has been cancelled" in store.get("booking-78")["data"]["carrier_status"]["text"]
    assert "has been cancelled" in json.dumps(store.get("session-78")["data"]["items"])  # the session heard it


def test_an_import_is_named_out_of_our_service_not_asked_back():
    """Sam's probe, Sun 00:30: ORD to FRA was answered "which German departure airport?". We export from Germany: the
    tool says so, and that it is no question for the customer."""
    from app.forwarder import normalise
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    s = {"origin_airport": "ORD", "pickup": None, "destination_airport": "FRA",
         "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
         "lots": [{"pieces": 2, "weight": q(300, "kg"), "volume": q(1.2, "cbm"), "dimensions": None}]}
    r = normalise(s, kit.world())
    assert any("out of our service" in x and "into Germany" in x for x in r["missing"])
    r = normalise({**s, "destination_airport": "LOS"}, kit.world())
    assert any("not one of our departure airports" in x for x in r["missing"])
    r = normalise({**s, "origin_airport": "FRA", "destination_airport": "LOS"}, kit.world())
    assert not r["missing"]


def test_an_option_id_names_one_option_for_the_life_of_the_deal():
    """Sam's probe, Sun 00:30: two shipments in one mail, two quotes; the second pricing renamed A1 and book("A1")
    would have booked it. Rounds 86-87: the goods changed after the quote. A changed shipment prices as B1, B2...,
    and the option quoted first stays bookable under its own id."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("ana@ana.example", "Two shipments", "320 kg FRA to ORD, and 900 kg FRA to ORD, cheapest")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = lambda kg: {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
                       "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
                       "lots": [{"pieces": 1, "weight": q(kg, "kg"), "volume": q(1.0, "cbm"), "dimensions": None}]}
    first = tools.get_offers(ctx, ship(320), "cheapest", 5)
    a = first["options"][0]
    assert a["option"].startswith("A")
    second = tools.get_offers(ctx, ship(900), "cheapest", 5)
    assert all(o["option"].startswith("B") for o in second["options"])
    opts = store.get(ctx.deal_id)["data"]["options"]
    assert opts[a["option"]]["total_text"] == a["total"]  # the first quote's option is still the one it was
    again = tools.get_offers(ctx, None, "cheapest", 0)  # waiting again does not start a new set
    assert all(o["option"].startswith("B") for o in again["options"])


def test_two_shipments_of_one_deal_are_two_bookings():
    """Round 89: GRU and TLV priced in one thread, GRU booked "now", TLV "later". The booking took the route and
    weight of the last pricing (TLV) and a second booking would have overwritten the first record."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("ana@ana.example", "Two shipments", "320 kg FRA to ORD, and 900 kg FRA to ORD, fastest")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = lambda kg: {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
                       "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
                       "lots": [{"pieces": 1, "weight": q(kg, "kg"), "volume": q(1.0, "cbm"), "dimensions": None}]}
    a = tools.get_offers(ctx, ship(320), "fastest", 5)["options"][0]["option"]
    b = tools.get_offers(ctx, ship(900), "fastest", 5)["options"][0]["option"]
    first = tools.book(ctx, a)
    assert first["weight_kg"] == "320" and first["team_reference"] == f"SM-{rfq['id']}"
    second = tools.book(ctx, b)
    assert second["weight_kg"] == "900" and second["team_reference"] == f"SM-{rfq['id']}-2"
    assert store.get(f"booking-{rfq['id']}")["data"]["weight_kg"] == "320"  # the first record is still the first
    assert store.get(f"booking-{rfq['id']}-2")["data"]["weight_kg"] == "900"
    found = tools.crm(ctx, "ORD")["matches"][0]
    assert {x["weight_kg"] for x in found["all_bookings"]} == {"320", "900"}
    assert tools.book(ctx, a)["team_reference"] == f"SM-{rfq['id']}"  # booking an option again keeps its own


def test_the_agent_writes_to_one_carrier_at_most_twice_in_ten_minutes():
    """Round 88: six cancellation mails to one airline in six minutes (each automatic answer woke the session for
    one more); 5U took 20 points off the round. Never spam a counterpart: the tool says no to a third mail."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    store.put("deal-79", "deal", "booked", {"root": 79, "asked": {}})
    ctx = tools.Ctx(f, "session-79", "deal-79", 79, "customer", None)
    to_airline = lambda: tools.mail_carrier(ctx, "meridian-freightways@hackloop.mail", "Cancel", "Please cancel.", None)
    assert "sent" in to_airline() and "sent" in to_airline()
    third = to_airline()
    assert "error" in third and "twice" in third["error"]
    assert "sent" in tools.mail_carrier(ctx, "solace-air-cargo@hackloop.mail", "Q", "A question.", None)


def test_cargo_insurance_on_the_customers_terms_is_in_every_total():
    """Round 91: "include cargo insurance in the all-in price: goods value 22000 EUR, insured at 110 % of that value,
    premium rate 0.40 %" = 96.80 EUR, added by code to every option, never by the model."""
    from decimal import Decimal
    from app import pricing, tools
    assert pricing.insurance_premium({"goods_value": 22000, "currency": "EUR", "insured_percent": 110,
                                      "premium_percent": 0.40, "minimum_premium": None}) == Decimal("96.80")
    assert pricing.insurance_premium({"goods_value": 1000, "currency": "EUR", "insured_percent": None,
                                      "premium_percent": 0.5, "minimum_premium": 25}) == Decimal("25.00")
    assert pricing.insurance_premium({"goods_value": 1000, "currency": "USD", "insured_percent": None,
                                      "premium_percent": 0.5, "minimum_premium": None}) is None
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("sara@lind.example", "Quote", "176 kg FRA to ORD, insured")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
            "cargo": {"commodity": "parts", "ready_date": "2026-11-29", "notes": None},
            "lots": [{"pieces": 1, "weight": q(176, "kg"), "volume": q(1.26, "cbm"), "dimensions": None}],
            "insurance": None}
    plain = tools.get_offers(ctx, ship, "fastest", 5)
    ins = {"goods_value": 22000, "currency": "EUR", "insured_percent": 110, "premium_percent": 0.40,
           "minimum_premium": None}
    insured = tools.get_offers(ctx, {**ship, "insurance": ins}, "fastest", 0)  # the same goods: no new asks
    assert insured["insurance"]["premium"] == "96.80 EUR"
    by = {o["airline"]: Decimal(o["total"].split()[0]) for o in plain["options"]}
    for o in insured["options"]:
        assert Decimal(o["total"].split()[0]) - by[o["airline"]] == Decimal("96.80")


def test_charges_the_customer_states_are_added_by_code():
    """The kind of round 91, generalised: a charge the customer tells us to include on their own amount or rate
    (a broker's fee, a handling fee per kg or in percent) is added by code to every total, never by the model."""
    from decimal import Decimal
    from app import pricing, tools
    fee = lambda a, b, cur="EUR": {"label": "x", "amount": a, "currency": cur, "basis": b}
    assert pricing.extra_charges([fee(85, "per_shipment"), fee(0.10, "per_kg"), fee(2, "percent_of_freight", None)],
                                 Decimal("1000"), Decimal("200")) == (Decimal("125.00"), [])
    total, skipped = pricing.extra_charges([fee(50, "per_shipment", "USD")], Decimal("1000"), Decimal("200"))
    assert total == 0 and skipped
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("sara@lind.example", "Quote", "176 kg FRA to ORD, with our broker's fee")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
            "cargo": {"commodity": "parts", "ready_date": "2026-11-29", "notes": None},
            "lots": [{"pieces": 1, "weight": q(176, "kg"), "volume": q(0.5, "cbm"), "dimensions": None}],
            "insurance": None, "extra_charges": []}
    plain = tools.get_offers(ctx, ship, "fastest", 5)
    with_fee = tools.get_offers(ctx, {**ship, "extra_charges": [fee(85, "per_shipment")]}, "fastest", 0)
    by = {o["airline"]: Decimal(o["total"].split()[0]) for o in plain["options"]}
    assert with_fee["extra_charges"]["included_in_every_total"] == ["x"]
    for o in with_fee["options"]:
        assert Decimal(o["total"].split()[0]) - by[o["airline"]] == Decimal("85.00")


def test_an_airline_confirming_the_flight_price_of_an_insured_booking_changes_nothing():
    """Round 92: the all-in total had the pickup and the insurance; the airline confirmed the flight price we booked,
    and the code took the rest for the pickup alone, called it a lower price and the customer heard 3301.88 instead
    of 3569.18. The rest of the all-in is everything besides the flight."""
    from app.forwarder import price_in_airline_mail, confirmation_matches
    b = {"amount": "3569.18 EUR", "others": "519.68", "pickup": {"total": "252.38"}, "booking_reference": "BK-PSPNO8HE",
         "via": "portal"}
    mail = "your booking BK-PSPNO8HE is confirmed.\nPrice: 3049.50 EUR\nStatus: booked and ready to ship"
    out, facts, changed = price_in_airline_mail(b, mail, True)
    assert not changed and out["amount"] == "3569.18 EUR" and "3569.18 EUR" in facts
    assert confirmation_matches(b, mail)


def test_a_portal_outage_is_retried_while_the_carriers_are_awaited(monkeypatch):
    """Round 93: '503 The rate API is unavailable' for the two fastest airlines, which sell only on the portal; the
    portal was asked once, the quote went out without them, 'too low to be right'. Now it is tried again while we
    wait, and waited for like a carrier's answer."""
    from app import tools
    from app.forwarder import Forwarder
    monkeypatch.setattr(Forwarder, "PORTAL_RETRY", (0, 90))
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    real, calls = api.rate, {"n": 0}

    def down_first(*a, **k):
        calls["n"] += 1
        return {"error": True, "status": 503, "detail": "The rate API is unavailable."} if calls["n"] <= 2 else real(*a, **k)
    api.rate = down_first
    rfq = api.customer("mira@nord.example", "Quote", "102 kg FRA to ORD, fastest")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
            "cargo": {"commodity": "parts", "ready_date": "2026-11-25", "notes": None},
            "lots": [{"pieces": 10, "weight": q(102, "kg"), "volume": q(0.76, "cbm"), "dimensions": None}],
            "insurance": None, "extra_charges": []}
    out = tools.get_offers(ctx, ship, "fastest", 20)
    assert any(o["source"] == "portal" for o in out["options"])
    assert not store.get(ctx.deal_id)["data"]["portal_retry"]["names"]


def test_while_the_rate_api_is_down_an_airline_is_priced_from_its_own_portal_rate():
    """Rounds 93-94: the rate API answered 503 for minutes and the portal airlines answer no mail; quoted without
    them, 'too low' (0 of 13 teams accepted round 93). A portal price is a rate per kg per airline, lane and weight
    break, stable all night: remembered, it prices the airline while the portal is down, marked as such."""
    from decimal import Decimal
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = lambda kg: {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
                       "cargo": {"commodity": "parts", "ready_date": "2026-11-25", "notes": None},
                       "lots": [{"pieces": 1, "weight": q(kg, "kg"), "volume": q(0.5, "cbm"), "dimensions": None}],
                       "insurance": None, "extra_charges": []}

    def ctx_for(who):
        rfq = api.customer(who, "Quote", "FRA to ORD")
        for m in api.poll(0)[0]:
            store.save_mail(m, "in", handled=True)
        return tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    seen = tools.get_offers(ctx_for("a@a.example"), ship(600), "cheapest", 5)
    live = {o["airline"]: Decimal(o["total"].split()[0]) for o in seen["options"] if o["source"] == "portal"}
    assert live
    api.rate = lambda *a, **k: {"error": True, "status": 503, "detail": "The rate API is unavailable."}
    down = tools.get_offers(ctx_for("b@b.example"), ship(700), "cheapest", 1)
    mem = {o["airline"]: o for o in down["options"] if o["source"] == "portal_memory"}
    assert set(mem) == set(live)
    for name, o in mem.items():  # the same rate per kg, at the new weight
        assert Decimal(o["total"].split()[0]) == (live[name] / 600 * 700).quantize(Decimal("0.01")) or \
            abs(Decimal(o["total"].split()[0]) - live[name] / 600 * 700) < Decimal("0.05")
        assert "unavailable" in o["carrier_note"]


def test_a_booking_is_cancelled_with_5u_and_the_crm_says_so():
    """5U's DELETE /v1/portal/bookings/{ref} (new, Sun): round 88 wrote six mails to an airline's quote desk instead,
    the booking was never cancelled, -20. Cancelling is a tool; tracking then reads a cancelled shipment."""
    from app import tools
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("petra@hof.example", "Quote", "320 kg FRA to ORD, cheapest")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
            "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
            "lots": [{"pieces": 1, "weight": q(320, "kg"), "volume": q(1.0, "cbm"), "dimensions": None}],
            "insurance": None, "extra_charges": []}
    opt = next(o["option"] for o in tools.get_offers(ctx, ship, "cheapest", 5)["options"] if o["source"] == "portal")
    b = tools.book(ctx, opt)
    ref = b["booking_reference"]
    tracking = tools.Ctx(f, "session-x", "deal-x", 1, "tracking", None)
    assert "error" in tools.cancel_booking(tracking, ref, ctx.deal_id)  # the tracking desk does not cancel
    assert "error" in tools.cancel_booking(ctx, "BK-NOPE")
    out = tools.cancel_booking(ctx, ref)
    assert out["status"] == "cancelled"
    assert store.get(f"booking-{rfq['id']}")["data"]["status"] == "cancelled"
    assert store.get(ctx.deal_id)["status"] == "cancelled"
    found = tools.crm(ctx, ref)["matches"][0]
    assert "cancelled" in found["booking"]["expected_stage_now"]


def test_an_airline_off_the_portal_for_this_lane_is_asked_by_mail_without_holding_the_quote():
    """5U moves carriers between the portal and mail (Sun 01:40). An airline that sells on the portal elsewhere and
    flies to the destination, but is not on the portal for this lane, was asked nowhere; a 404 had no fallback.
    Both are now asked by mail, and not waited for (round 94: waiting for airlines that never wrote)."""
    from app import tools
    from app.forwarder import waiting_for
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    w = kit.world()
    off = w.portal_airlines_off_lane("FRA", "ORD")
    on = {a["name"] for a in w.portal.get(("FRA", "ORD"), [])}
    assert all(c.name not in on for c in off)
    rfq = api.customer("a@a.example", "Quote", "320 kg FRA to ORD")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
            "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
            "lots": [{"pieces": 1, "weight": q(320, "kg"), "volume": q(1.0, "cbm"), "dimensions": None}],
            "insurance": None, "extra_charges": []}
    tools.get_offers(ctx, ship, "cheapest", 0)
    d = store.get(ctx.deal_id)["data"]
    asked_mail = set(d["asked"].values())
    assert {c.email for c in off} <= asked_mail  # asked
    assert not ({c.email for c in off} & set(waiting_for({**d, "replied": []})))  # but not awaited


def test_one_weight_for_all_lots_is_counted_once():
    """Sam's probe: '2 different pallets, 480 kg in total' was asked back, or counted on each lot (960 kg, +78 %).
    A weight or volume for all lots together goes in totals and counts once."""
    from app.forwarder import normalise
    q = lambda v, u, pp=False: {"value": v, "unit": u, "per_piece": pp}
    none = q(None, None)
    s = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
         "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
         "lots": [{"pieces": 1, "weight": none, "volume": none,
                   "dimensions": {"length": 120, "width": 80, "height": 100, "unit": "cm"}},
                  {"pieces": 1, "weight": none, "volume": none,
                   "dimensions": {"length": 120, "width": 100, "height": 80, "unit": "cm"}}],
         "totals": {"weight": q(480, "kg"), "volume": none}}
    r = normalise(s, kit.world())
    assert not r["missing"] and r["weight_kg"] == "480" and r["volume_cbm"] == "1.92" and r["pieces"] == 2
    r = normalise({**s, "totals": None, "lots": [{"pieces": 8, "weight": q(22, "kg", True),
                                                   "volume": q(0.25, "cbm", True), "dimensions": None}]}, kit.world())
    assert r["weight_kg"] == "176" and r["volume_cbm"] == "2"


def test_a_bid_without_a_readable_time_is_marked_and_cannot_be_the_fast_one():
    """The mark is set where the bid is read, and the options the agent sees use it (round 69)."""
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    trucker = next(c for c in kit.world().carriers if c.kind == "trucker")
    read = {"available": True, "total": 176.71, "currency": "EUR", "time_value": None, "time_unit": None, "reference": "TRK-9"}
    unread = f.offer(read, {"id": 5, "sender": trucker.email, "body": "Our total is 176.71 EUR, we collect once the driver is back."}, trucker)
    stated = f.offer(read, {"id": 6, "sender": trucker.email, "body": "Our total is 176.71 EUR. Pickup time: 3 hours."}, trucker)
    assert unread.extra.get("time_unknown") is True and "time_unknown" not in stated.extra and stated.days > 0


def test_a_file_is_read_for_what_it_is_not_for_its_name():
    """5U said the files get stranger, and since round 84 a round few teams can read pays a multiple. The reader went
    by the name's ending alone: a pdf called offer.dat, a workbook with no ending, a tiff from a scanner, an old Word
    file all came back as "binary attachment"."""
    import io
    import zipfile
    from pathlib import Path
    from PIL import Image
    from app import docs, llm
    data = Path(__file__).parent / "data"
    xls, doc = (data / "packing-list.xls").read_bytes(), (data / "request.doc").read_bytes()
    assert docs.kind("list.dat", xls) == ".xls" and "Total gross weight kg\t356" in docs.text("list", xls)
    booking = "Booking confirmation, 320 kg".encode("utf-16-le")  # a Word file or an Outlook mail that says "Booking"
    assert docs.kind("a", doc + booking) == ".ole"
    assert docs.kind("b", doc[:512] + "__substg1.0_1000001F".encode("utf-16-le") + booking) == ".ole"
    word = docs.text("request.doc", doc)
    assert "total gross weight 486 kg, from Stuttgart to São Paulo (GRU)" in word and "Jürgen Weiß" in word
    assert "binary attachment" not in docs.text("anfrage", doc)                      # the same file without an ending
    rtf = rb"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0\fs24 Total weight: 320 kg\par Gr\'f6\'dfe 120x80x95 cm\par}"
    assert docs.text("offer.txt", rtf) == "Total weight: 320 kg\nGröße 120x80x95 cm"
    deck = io.BytesIO()
    with zipfile.ZipFile(deck, "w") as z:
        z.writestr("ppt/presentation.xml", "<p/>")
        z.writestr("ppt/slides/slide1.xml", "<a:p><a:r><a:t>Rate FRA-ORD 2.59 EUR/kg</a:t></a:r></a:p><a:p><a:r><a:t>Minimum 95 &amp; fuel 0.80</a:t></a:r></a:p>")
    assert docs.text("rates.bin", deck.getvalue()) == "Rate FRA-ORD 2.59 EUR/kg\nMinimum 95 & fuel 0.80"
    assert docs.kind("BMW.txt", b"BMW parts, 3 crates") == ".txt" and docs.kind("a.csv", b"kg;cbm\n320;1,5") == ".csv"
    seen, real = [], llm.look
    llm.look = lambda mime, raw, run_id=None: seen.append((mime, raw[:4])) or "Our total is 340.60 EUR"
    try:
        for fmt, name in (("TIFF", "scan.tif"), ("BMP", "offer.bmp"), ("PNG", "photo.jpeg"), ("JPEG", "no-ending"), ("PNG", "rates.txt")):
            b = io.BytesIO()
            Image.new("RGB", (40, 20), (200, 30, 30)).save(b, fmt)
            assert "340.60 EUR" in docs.text(name, b.getvalue()), name
    finally:
        llm.look = real
    assert [m for m, _ in seen] == ["image/png", "image/png", "image/png", "image/jpeg", "image/png"]
    assert all(head in (b"\x89PNG", b"\xff\xd8\xff\xe0") for _, head in seen)       # tiff and bmp reach the model as png


def test_a_tariffs_validity_without_a_year_is_the_nearest_such_day():
    """333de15 made a day without a year the next such day. For a ready date that is right; a tariff "valid from
    1 November" read on 22 November then started in 2027 and never priced a shipment."""
    from datetime import date, timedelta
    from app.forwarder import _day
    today = date.today()
    began = today - timedelta(days=21)
    said = f"{began.day} {began.strftime('%B')}"
    assert _day(said, nearest=True) == began.isoformat()                    # three weeks ago, not next year
    assert _day(said) == began.replace(year=began.year + 1).isoformat()     # a ready date still lies ahead
    ends = today + timedelta(days=9)
    assert _day(f"{ends.day} {ends.strftime('%B')}", nearest=True) == ends.isoformat()
    assert _day("2026-12-01", nearest=True) == "2026-12-01" and _day("whenever", nearest=True) is None


def test_places_are_understood_as_their_people_write_them():
    """A German customer writes München, Köln, Düsseldorf, Gießen; the kit names the zones Munich, Cologne, Duesseldorf,
    Giessen. Passed on as written, the town was "not inside our pickup zones" and the customer got a question instead
    of a price, which 5U scores as a decline. The same for São Paulo and Pékin as destinations."""
    from app.forwarder import normalise
    api = FakeFiveU()
    w = kit.load(api)
    zone = lambda town: kit.zone_of_town(town, w.zones)
    assert [zone(t) for t in ("München", "Muenchen", "Munchen", "Munich")] == ["80"] * 4
    assert [zone(t) for t in ("Köln", "Koeln", "Düsseldorf", "Gießen", "Mönchengladbach", "Tübingen")] == ["50", "50", "40", "35", "41", "72"]
    assert zone("Munich South depot") == "81" and zone("München Süd") == "81" and zone("Hamburg North warehouse") == "22"
    assert zone("Frankfurt") == "60" and zone("Hamburg") == "20" and zone("Berlin") is None and zone("Hessen") is None
    code = kit.destination_code
    assert [code(t) for t in ("São Paulo", "Pékin", "Neu-Delhi", "Nueva York", "Tokio", "Mexiko-Stadt")] == ["GRU", "PEK", "DEL", "JFK", "NRT", "MEX"]
    assert code("Lagos, Nigeria") == "LOS" and code("LOS") == "LOS" and code("Limassol") is None and code("Chicago or New York") == "ORD"
    lot = [{"pieces": 2, "weight": {"value": 300, "unit": "kg", "per_piece": False}, "volume": {"value": 1, "unit": "cbm", "per_piece": False}}]
    req = normalise({"origin_airport": None, "destination_airport": "São Paulo", "lots": lot,
                     "pickup": {"city": "München", "postcode": None}, "cargo": {}}, w)
    assert req["missing"] == [] and (req["origin"], req["destination"], req["pickup_zone"]) == ("MUC", "GRU", "80")
    # only the first digits of a postcode: the truckers still get five (they answer nothing else)
    sent = []
    f = Sync(api)
    f.mail_carrier = lambda deal_id, to, subject, body, in_reply_to=None: sent.append(body) or 1
    trucker = next(c for c in w.carriers if c.kind == "trucker")
    f.ask_trucker("deal-1", trucker, {**req, "pickup_postcode": "80", "weight_kg": "300", "volume_cbm": "1.000", "pieces": 2})
    f.ask_trucker("deal-1", trucker, {**req, "pickup_postcode": "80469", "weight_kg": "300", "volume_cbm": "1.000", "pieces": 2})
    assert "pickup from 80331 Munich" in sent[0] and "pickup from 80469 Munich" in sent[1]


def test_dates_units_and_text_files_as_people_write_them():
    """A date in German, French, Italian or Spanish, or with an ordinal, was not a date: the ready date fell back to
    today and the dates in the quote were wrong. cm³ and dm³ were unknown units (no price, a question instead). A
    csv saved as UTF-16 without its mark came back as "binary attachment". (ergebnis_8_kanten.md, cases 13, 15, 22)"""
    from datetime import date, timedelta
    from decimal import Decimal
    from app import docs, language
    from app.forwarder import _day
    assert [_day(t) for t in ("1. Dezember 2026", "December 1st, 2026", "le 1 décembre 2026", "il 1 dicembre 2026",
                              "1 de diciembre de 2026", "1 Dec 2026", "01.12.2026", "01.12.26")] == ["2026-12-01"] * 8
    today = date.today()
    monday = (today + timedelta(days=(0 - today.weekday() - 1) % 7 + 1)).isoformat()
    assert _day("Montag") == monday == _day("lundi") == _day("Monday") and _day("morgen") == _day("tomorrow")
    tuesday = (today + timedelta(days=(1 - today.weekday() - 1) % 7 + 1)).isoformat()
    thursday = (today + timedelta(days=(3 - today.weekday() - 1) % 7 + 1)).isoformat()
    assert _day("Tuesday") == _day("next Tuesday") == _day("Tue") == _day("Dienstag") == tuesday   # fold: "tusday"
    assert _day("jueves") == _day("Thursday") == thursday and _day("aujourd'hui") == today.isoformat()
    assert _day("KW 48") is None and _day("whenever") is None                 # not guessed: it stays the customer's words
    lots = [{"pieces": 2, "weight": {"value": 25, "unit": "kg", "per_piece": True},
             "volume": {"value": 500000, "unit": "cm³", "per_piece": True}}]
    assert language.unknown_units(lots) == [] and language.volume_cbm(lots[0]["volume"], [], 2) == Decimal("1.000000")
    assert language.volume_cbm({"value": 1000, "unit": "dm³", "per_piece": False}, [], 1) == 1
    assert language.unit("Kubikmeter") in language.VOLUME and language.unit("mètres cubes") in language.VOLUME
    wide = "Gross weight kg;320\nVolume cbm;1,5\nDestination;São Paulo".encode("utf-16-le")
    assert docs.text("details.csv", wide) == "Gross weight kg;320\nVolume cbm;1,5\nDestination;São Paulo"
    assert docs.text("details.csv", b"Gross weight kg;320\nVolume cbm;1,5") == "Gross weight kg;320\nVolume cbm;1,5"


def test_a_picture_inside_a_document_is_read_when_it_is_content():
    """A Word letter that says "see the shipping particulars below" with a scan pasted in, a pdf page with a paragraph
    above a pasted scan: the reader passed the words on and left the picture, where the weight or the price was
    (ergebnis_8_kanten.md, cases 1 and 7). A logo is still not read: every picture read is a model call."""
    import io
    import os
    import zlib
    from docx import Document
    from PIL import Image
    from app import docs, llm
    scan, logo = io.BytesIO(), io.BytesIO()
    Image.frombytes("RGB", (200, 200), os.urandom(200 * 200 * 3)).save(scan, "PNG")      # noise: a big file, like a scan
    Image.new("RGB", (40, 20), (200, 30, 30)).save(logo, "PNG")
    assert len(scan.getvalue()) >= docs.MATERIAL > len(logo.getvalue())
    letter = Document()
    letter.add_paragraph("See the attached shipping particulars.")
    letter.add_picture(io.BytesIO(logo.getvalue()))
    letter.add_picture(io.BytesIO(scan.getvalue()))
    word = io.BytesIO()
    letter.save(word)
    seen, real = [], llm.look
    llm.look = lambda mime, raw, run_id=None: seen.append(len(raw)) or "FRA-ASU, 100 kg, 0.1 cbm"
    try:
        out = docs.text("request.docx", word.getvalue())
        assert out.startswith("See the attached shipping particulars.") and "FRA-ASU, 100 kg, 0.1 cbm" in out
        assert len(seen) == 1 and seen[0] >= docs.MATERIAL                                  # the scan, not the logo
    finally:
        llm.look = real


def test_a_change_in_how_5u_scores_is_logged_once():
    """The board's `rules` (18 minute cost window since Sat 21:00) changed once without a word, and 5U announced a
    new scoring algorithm (Sun 00:04): the watcher says so in the journal the moment the board shows it."""
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    rules = {"accuracy_points": 45, "time_points": 15, "cost_points": 40, "cost_window_minutes": 18}
    r40 = {"round_no": 40, "sent_at": "2026-11-21T18:57:47.787398+00:00", "answered_at": "2026-11-21T18:58:27.538195+00:00",
           "verdict": "accepted", "reason": None, "points": {"time": 15.0, "accuracy": 45.0}}
    said = lambda: [e["summary"] for e in store.events(limit=500) if e["agent"] == "watcher" and e["kind"] == "error"]
    f.watch_scoring({"requests": [r40]}, {"rules": rules, "frozen_at": None})   # the first look is the baseline
    f.watch_scoring({"requests": [r40]}, {"rules": rules, "frozen_at": None})
    assert said() == []
    r41 = {"round_no": 41, "sent_at": "2026-11-21T19:03:52+00:00", "answered_at": "2026-11-21T19:04:36+00:00",
           "verdict": "rejected", "reason": "declined_out_of_scope", "points": {"time": 9.5, "accuracy": 45.0, "followup": 5.0}}
    r40b = {**r40, "points": {"time": 15.0, "accuracy": 40.5, "cost": 39.1}}   # cost arrives late, accuracy moved
    new = {"requests": [r41, r40b]}, {"rules": {**rules, "time_points": 25}, "frozen_at": "2026-11-22T09:00:00+00:00"}
    f.watch_scoring(*new)
    f.watch_scoring(*new)   # the same board again says nothing new
    out = said()
    assert len(out) == 6 and len(set(out)) == 6
    assert any("changed the board rules" in s and "'time_points': 25" in s for s in out)
    assert any("frozen" in s for s in out) and any("followup" in s for s in out)
    assert any("declined_out_of_scope" in s for s in out)
    assert any("points of 1 earlier results moved: round 40 accuracy 45.0 -> 40.5" in s for s in out)
    assert any("round 41 answered in 44 s took 9.5 of 25" in s and "round 40" not in s for s in out)
    # Sun 00:27: from round 84 a round few teams get right pays a multiple; a multiplied round we lost stands out
    r84 = {"round_no": 84, "verdict": "rejected", "reason": "too_high", "points": {}, "multiplier": 3, "closed": True}
    r85 = {"round_no": 85, "verdict": "accepted", "reason": None, "points": {}, "multiplier": 1, "closed": True}
    r86 = {"round_no": 86, "verdict": "pending", "reason": None, "points": {}, "multiplier": 5, "closed": False}
    board = {"rules": {**rules, "time_points": 25}, "frozen_at": "2026-11-22T09:00:00+00:00",
             "rounds": [{"round_no": 84, "accepted": 2, "multiplier": 3}, {"round_no": 85, "accepted": 9, "multiplier": 1}]}
    f.watch_scoring({"requests": [r86, r85, r84, r41, r40b]}, board)
    f.watch_scoring({"requests": [r86, r85, r84, r41, r40b]}, board)
    more = [s for s in said() if s not in out]
    assert len(more) == 3   # the multiplied round, the new fields, the reason code not seen before
    assert any("round 84 pays a multiple (3), 2 teams accepted; ours: rejected too_high" in s for s in more)
    assert any("new field on the board" in s and "requests.multiplier" in s and "rounds.multiplier" in s for s in more)
    assert not any("round 86" in s for s in more)        # still open: its multiple and our verdict are not final
    # deployed mid-game (no baseline yet): the multiplied rounds so far are said on the first look, nothing else is
    store.kv_set("board_scoring", "null")
    f.watch_scoring({"requests": [r86, r85, r84, r41, r40b]}, board)
    again = said()
    assert sum("round 84 pays a multiple" in s for s in again) == 2 and len(again) == len(out) + len(more) + 1
    # the board as it really is (read Sun 00:52): the multiple is `factor` on the public round, a string, null without
    store.kv_set("board_scoring", "null")
    real = {"rules": {**rules, "few_winners": {"factors": ["5", "3", "2"], "from_round": 84}}, "frozen_at": None,
            "rounds": [{"round_no": 90, "status": "closed", "answered": 13, "accepted": 2, "factor": "3"},
                       {"round_no": 89, "status": "closed", "answered": 12, "accepted": 12, "factor": None}]}
    r90 = {"round_no": 90, "verdict": "rejected", "reason": "no_pdf_offer", "points": {}, "closed": True}
    r89 = {"round_no": 89, "verdict": "accepted", "reason": None, "points": {"time": 15.0, "accuracy": 45.0}, "closed": True}
    before = len(said())
    f.watch_scoring({"requests": [r90, r89]}, real)
    assert [s for s in said()][before:] == ["scoring: round 90 pays a multiple (3), 2 teams accepted; ours: rejected no_pdf_offer"]
    # our requests as the board really gives them carry no `closed`: the public round's status settles it
    store.kv_set("board_scoring", "null")
    real["rounds"].append({"round_no": 91, "status": "open", "answered": 3, "accepted": 1, "factor": "5"})
    r90, r91 = {k: v for k, v in r90.items() if k != "closed"}, {"round_no": 91, "verdict": "pending", "points": {}}
    before = len(said())
    f.watch_scoring({"requests": [r91, r90, r89]}, real)
    assert [s for s in said()][before:] == ["scoring: round 90 pays a multiple (3), 2 teams accepted; ours: rejected no_pdf_offer"]
    # a board in a shape nobody foresaw is compared as far as it goes and never raises into the watcher
    f.watch_scoring({"requests": ["row", r84], "frozen_at": None}, {"rules": "changed", "rounds": {"84": {}}, "ranking": None})


def test_a_person_enters_a_portal_page_rate_while_the_rate_api_is_down():
    """Rounds 93-98: the rate API answered 503 for some airlines; 5U's portal page still shows them, to people who
    pass its check. With operator mode on, the agent waits for a person's price (up to 80 s after the mail); the
    price joins the offers like a portal price, and every total is still computed by code."""
    from decimal import Decimal
    from app import tools
    from app.forwarder import add_portal_page_rate, waiting_for
    api = FakeFiveU()
    kit.load(api)
    f = Sync(api)
    api.rate = lambda *a, **k: {"error": True, "status": 503, "detail": "The rate API is unavailable."}
    store.kv_set("operator_on", "1")
    rfq = api.customer("k@k.example", "Quote", "320 kg FRA to ORD")
    for m in api.poll(0)[0]:
        store.save_mail(m, "in", handled=True)
    ctx = tools.Ctx(f, f"session-{rfq['id']}", f"deal-{rfq['id']}", rfq["id"], "customer", store.thread(rfq["id"])[0])
    q = lambda v, u: {"value": v, "unit": u, "per_piece": False}
    ship = {"origin_airport": "FRA", "pickup": None, "destination_airport": "ORD",
            "cargo": {"commodity": "parts", "ready_date": "2026-11-26", "notes": None},
            "lots": [{"pieces": 1, "weight": q(320, "kg"), "volume": q(1.0, "cbm"), "dimensions": None}],
            "insurance": None, "extra_charges": []}
    first = tools.get_offers(ctx, ship, "fastest", 0)
    d = store.get(ctx.deal_id)["data"]
    missing = [a["name"] for a in d["portal_missing"]["airlines"]]
    assert missing and first["portal_page"]["person_at_desk"]  # the agent is told, and drives the page itself
    assert not any(x.startswith("person:") for x in waiting_for(d))  # get_offers does not block on a person
    out = add_portal_page_rate(ctx.deal_id, missing[0], "1696,00", 1, "R-page1")
    assert out["ok"] and out["offer"]["source"] == "portal_page"
    opts = tools.get_offers(ctx, None, "fastest", 0)["options"]
    page = next(o for o in opts if o["airline"] == missing[0])
    assert page["total"] == "1696.00 EUR" and page["bookable_reference"] == "R-page1"
    store.kv_set("operator_on", "0")
    assert "operator mode off" in tools.portal_page(ctx, "ask_person", airline=missing[0])["error"]
