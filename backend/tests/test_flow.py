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
         "transit_days": 4, "pickup_hours": None, "reference": "R-9", "valid_until": None, "note": None}
    m = {"id": 42, "in_reply_to": 41, "sender": "yellowtail-air-freight@hackloop.mail"}
    off = f.offer(o, m, kit.world().carrier_by_email(m["sender"]))
    assert str(off.total) == "982.00"  # 300 x 2.42 + 300 x 0.77 + 25


# ---- likely changes that would stop us before a quote fails (docs/likely-changes.md 3, 5, 9, 10) ---------------

def test_the_forwarder_starts_while_the_portal_is_down():
    """A restart during a portal outage must not stop the mailbox: sheets and carriers still price."""
    class Down(FakeFiveU):
        def ports(self):
            raise RuntimeError("503 portal unavailable")
    kit.load(FakeFiveU())                                   # a normal start remembers the lane map in the register
    lanes = dict(kit.world().portal)
    assert lanes
    api = Down()
    kit.load(api)                                           # the restart: no exception
    assert kit.world().portal == lanes and kit.world().brackets
    f = Sync(api)
    rfq = api.customer("anna@acme.example", "Quote FRA to ORD", "Please quote 320 kg, 1.5 cbm, FRA to ORD, cheapest.")
    run(f)
    assert store.get(f"deal-{rfq['id']}")["status"] == "quoted"


def test_one_mail_that_cannot_be_sent_does_not_strand_the_pricing_run():
    """5U lowers a limit, or one send fails: that carrier is missing, everything else is priced."""
    class OneFails(FakeFiveU):
        def send(self, to, subject, body, in_reply_to=None):
            if to == "taunusfracht@hackloop.mail":
                raise RuntimeError("send to taunusfracht@hackloop.mail failed: 429")
            return super().send(to, subject, body, in_reply_to)
    api = OneFails()
    kit.load(api)
    f = Sync(api)
    rfq = api.customer("bob@beta.example", "Pickup in 60311", "Pickup at 60311 Frankfurt, 320 kg, 1.5 cbm, FRA to ORD, cheapest.")
    run(f, 4)
    deal = store.get(f"deal-{rfq['id']}")
    assert deal["status"] == "quoted" and deal["data"]["quote"]["pickup"]["carrier"]
    assert deal["data"]["not_asked"] == ["taunusfracht@hackloop.mail"]
    assert any(o["source"] == "portal" for o in deal["data"]["offers"]), "the portal was still read"
    assert "taunusfracht@hackloop.mail" not in deal["data"]["asked"].values()


def test_a_price_without_a_time_is_not_the_fastest_offer():
    """A trucker's new wording ("we collect next working day") leaves pickup_hours empty. Counted as zero hours it
    would win every fastest and every 50/50 pick."""
    from decimal import Decimal as D
    from app.pricing import Offer
    f = Sync(FakeFiveU())
    req = {"origin": "FRA", "destination": "ORD", "weight_kg": "320", "volume_cbm": None, "chargeable_kg": "320",
           "pieces": 1, "pickup_zone": "60", "pickup_postcode": "60311"}
    air = [Offer("air", "Slow", D(700), D(5), "sheet")]
    trucks = [Offer("pickup", "Bodenseefracht", D("88.60"), D("1.083"), "email"),
              Offer("pickup", "Taunusfracht", D("177.40"), D("0.125"), "email"),
              Offer("pickup", "Neuer Text Spedition", D("260.00"), D(0), "email", extra={"time_unknown": True})]
    store.put("deal-1", "deal", "pricing", {"root": 1, "request": req, "offers": [o.as_dict() for o in air + trucks]})
    out = f.options("deal-1", "cheapest")
    row = next(o for o in out["options"] if o["option"] == out["recommended"])
    assert row["pickup"]["trucker"] == "Taunusfracht"          # the 50/50 pick among what we know
    unknown = next(p for p in out["pickup_alternatives"] if p["trucker"] == "Neuer Text Spedition")
    assert unknown["pickup_hours"] is None                      # shown as unknown, not as 0 h
    m = {"id": 9, "sender": "taunusfracht@hackloop.mail"}
    o = f.offer({"available": True, "total": 120.0, "currency": "EUR", "pickup_hours": None, "transit_days": None,
                 "reference": "TRK-1"}, m, kit.world().carrier_by_email("taunusfracht@hackloop.mail"))
    assert o.extra["time_unknown"] is True
