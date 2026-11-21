from decimal import Decimal as D

from app import kit, language, pricing
from app.pricing import Offer


def lane(airline, o, d):
    return next(l for l in kit.world().sheet(o, d) if l["airline"] == airline)


def test_sheet_price_matches_live_email_bid():
    # Yellowtail answered 828.80 EUR by mail for FRA-ORD, 320 kg, 1.5 cbm (live, Sat 21 Nov)
    total, billed = pricing.sheet_price(lane("Yellowtail Air Freight", "FRA", "ORD"), D(320), D("1.5"))
    assert total == D("828.80") and billed == 320


def test_next_break_is_taken_when_cheaper():
    l = lane("Yellowtail Air Freight", "FRA", "ORD")  # +100 2.42, +250 1.82, surcharges 0.77
    total, billed = pricing.sheet_price(l, D(240), None)
    assert billed == 250 and total == pricing.money(D(250) * D("1.82") + D(250) * D("0.77"))
    assert total < pricing.money(D(240) * D("2.42") + D(240) * D("0.77"))


def test_volume_weight_and_minimum():
    l = lane("Yellowtail Air Freight", "FRA", "ORD")
    assert pricing.chargeable(D(100), D(1)) == D(167)
    total, _ = pricing.sheet_price(l, D(1), None)
    assert total == pricing.money(D(l["minimum_eur"]) + D("0.77"))


def test_pick_cheapest_fastest_balanced():
    a = Offer("air", "A", D(1000), D(5), "portal")
    b = Offer("air", "B", D(1200), D(1), "portal")
    c = Offer("air", "C", D(1010), D(4), "email")
    assert pricing.pick([a, b, c], "cheapest").carrier == "A"
    assert pricing.pick([a, b, c], "fastest").carrier == "B"
    assert pricing.pick([a, b, c], "unspecified").carrier == "B"  # 1.2 + 1 beats 1 + 5


def test_quote_adds_pickup_and_keeps_one_offer_per_carrier():
    air = [Offer("air", "A", D(900), D(3), "sheet"), Offer("air", "A", D(900), D(3), "email", "R-1")]
    pick = [Offer("pickup", "T1", D("177.40"), D("0.125"), "email"), Offer("pickup", "T2", D(150), D("0.2"), "email")]
    q = pricing.quote(air, pick, "cheapest", True, pickup_rule="cheapest")
    assert q["total"] == "1050.00" and q["air"]["rate_id"] == "R-1" and q["pickup"]["carrier"] == "T2"
    # the default (balanced, ratio): 177.40 / 150 + 3 h / 3 h beats 150 / 150 + 4.8 h / 3 h
    assert pricing.quote(air, pick, "cheapest", True)["pickup"]["carrier"] == "T1"
    assert pricing.quote(air, [], "cheapest", True) is None


def test_units():
    assert language.weight_kg({"value": 1000, "unit": "lb", "per_piece": False}, None) == D("453.59237")
    assert language.weight_kg({"value": 50, "unit": "kg", "per_piece": True}, 4) == 200
    dims = [{"count": 2, "length": 120, "width": 80, "height": 100, "unit": "cm"}]
    assert language.volume_cbm({"value": None, "unit": None, "per_piece": False}, dims, 2) == D("1.92")


def test_pickup_town_is_its_zone_and_no_place_is_missing():
    from app.forwarder import normalise
    p = {"pieces": 1, "weight": {"value": 100, "unit": "kg", "per_piece": False}, "volume": None, "dimensions": [],
         "pickup": {"postcode": None, "city": "Darmstadt"}, "origin_airport": None, "destination_airport": "JFK",
         "cargo": {"commodity": None, "ready_date": None, "notes": None}}
    r = normalise(p, kit.world())
    assert r["pickup_zone"] == "64" and r["origin"] == "FRA" and not r["missing"]  # round 20: a town is enough
    p["pickup"] = {"postcode": None, "city": None}  # "from our warehouse", no place given (rounds 15-18)
    assert normalise(p, kit.world())["missing"] == ["where to collect: the pickup postcode, or at least the town"]


def test_live_bid_beats_stale_sheet():
    sheet = Offer("air", "Yellowtail Air Freight", D(800), D(4), "sheet")
    mail = Offer("air", "Yellowtail Air Freight", D(850), D(4), "email", "R-1")
    only_sheet = Offer("air", "Orion Cargo Air", D(900), D(2), "sheet")
    best = {o.carrier: o for o in pricing.best_by_carrier([sheet, mail, only_sheet])}
    assert best["Yellowtail Air Freight"].total == 850 and best["Orion Cargo Air"].total == 900


# ---- pick rules (docs/challenges/5u-facts.md) ----------------------------------------------------------------

def zone_60():
    # live trucker bids, zone 60 -> FRA, Sat 21 Nov 14:10 UTC (mails 164-168): price EUR, pickup hours
    bids = [("Bodenseefracht", "88.60", 26), ("Westfalenroute", "96.80", 23), ("Isarwelle Spedition", "129.80", 16),
            ("Domblick Kurierdienst", "151.60", 15), ("Taunusfracht", "177.40", 3)]
    return [Offer("pickup", n, D(p), (D(h) / 24).quantize(D("0.001")), "email") for n, p, h in bids]


def test_balance_rules_disagree_on_live_trucker_bids():
    assert pricing.balanced(zone_60(), "ratio").carrier == "Taunusfracht"      # the fastest: 3 h outweighs 2x price
    assert pricing.balanced(zone_60(), "minmax").carrier == "Westfalenroute"   # 0.48: neither cheapest nor fastest


def test_minmax_with_two_offers_takes_the_cheaper():
    two = [Offer("pickup", "A", D(100), D(1), "email"), Offer("pickup", "B", D(150), D("0.2"), "email")]
    assert pricing.balanced(two, "minmax").carrier == "A"
    assert pricing.balanced([two[0]], "minmax").carrier == "A"


def test_pickup_rule_decides_the_all_in_total():
    air = [Offer("air", "Slow", D(700), D(5), "sheet"), Offer("air", "Fast", D(900), D(2), "sheet")]
    q = lambda pref, **kw: pricing.quote(air, zone_60(), pref, True, **kw)
    # `asked`: the trucker follows what the customer asked for
    assert q("cheapest", pickup_rule="asked")["total"] == "788.60"
    assert q("cheapest", pickup_rule="asked")["pickup"]["carrier"] == "Bodenseefracht"
    assert q("fastest", pickup_rule="asked")["total"] == "1077.40"
    assert q("fastest", pickup_rule="asked")["pickup"]["carrier"] == "Taunusfracht"
    # the fastest trucker costs 88.80 more than the cheapest: 9.0 % on this total, outside the 5 % band
    assert q("fastest", pickup_rule="cheapest")["total"] == "988.60"
    assert q("fastest", pickup_rule="balanced", balance="minmax")["total"] == "996.80"
    assert q("cheapest", pickup_rule="balanced", balance="minmax")["total"] == "796.80"
    assert q("cheapest", pickup_rule="balanced", balance="minmax")["air"]["carrier"] == "Slow"


def test_request_without_preference_follows_the_switch():
    air = [Offer("air", "Slow", D(700), D(5), "sheet"), Offer("air", "Mid", D(720), D(4), "sheet"),
           Offer("air", "Fast", D(900), D(2), "sheet")]
    q = lambda **kw: pricing.quote(air, [], "unspecified", False, **kw)["air"]["carrier"]
    assert q() == "Fast"                                   # default so far: ratio balance, speed dominates
    assert q(unspecified="cheapest") == "Slow"
    assert q(balance="minmax") == "Mid"                    # 0.05 + 0.33 beats 0 + 1 and 1 + 0


def test_breaks_to_try_for_a_carrier_without_known_breaks():
    assert pricing.breaks_to_try(D(280)) == [D(300)]
    assert pricing.breaks_to_try(D(230)) == [D(250), D(300)]   # third break is 250 or 300, depending on the airline
    assert pricing.breaks_to_try(D(120)) == []                 # 250 is more than 1.35x away: cannot be cheaper
    assert pricing.breaks_to_try(D(2500)) == []


def test_prices_in_other_currencies_convert_with_their_own_rate():
    rates: dict = {}
    assert pricing.to_eur(D("100"), "EUR", None, rates) == D("100.00")
    assert pricing.to_eur(D("100"), "USD", None, rates) is None             # no rate seen: dropped, never guessed
    assert pricing.to_eur(D("100"), "USD", "0.92", rates) == D("92.00")
    assert pricing.to_eur(D("100"), "GBP", "1.15", rates) == D("115.00")    # a GBP price brings its own rate
    assert pricing.to_eur(D("100"), "usd", None, rates) == D("92.00")       # and the USD rate is still the USD rate
    assert pricing.to_eur(D("100"), "USD", "n/a", rates) == D("92.00")      # an unreadable rate changes nothing


def test_balanced_ratio_trucker_matches_the_scored_rounds():
    """Live, Sat 21 Nov: 5U's best price used Westfalenroute in round 1 and Bodenseefracht in round 2. Only the
    ratio 50/50 rule picks both; cheapest misses round 1, fastest and minmax miss round 2."""
    t = lambda rows: [Offer("pickup", n, D(p), (D(h) / 24).quantize(D("0.001")), "email") for n, p, h in rows]
    r1 = t([("Elbkante Logistik", "134.69", 29), ("Westfalenroute", "220.03", 11),
            ("Maintal Transport Logistik", "222.36", 13), ("Bodenseefracht", "269.71", 12)])
    r2 = t([("Bodenseefracht", "119.01", 30), ("Nordlicht Haulage", "152.01", 30), ("Hansekogge Trucking", "245.02", 23),
            ("Westfalenroute", "266.03", 23), ("Spessart Spedition", "299.03", 25)])
    assert pricing.balanced(r1, "ratio").carrier == "Westfalenroute"
    assert pricing.balanced(r2, "ratio").carrier == "Bodenseefracht"
    assert pricing.pick(r1, "cheapest").carrier != "Westfalenroute" and pricing.balanced(r2, "minmax").carrier != "Bodenseefracht"


def test_timeline_starts_when_the_goods_are_ready():
    """Live round 1: booked Sat 21 Nov, ready 25 Nov, 1 day transit. Arrival is 26 Nov, not 22 Nov."""
    import time as _t
    from datetime import datetime, timezone
    from app import tools
    booked = datetime(2026, 11, 21, 15, 2, tzinfo=timezone.utc).timestamp()
    b = {"booked_at": booked, "ready_date": "2026-11-25", "transit_days": "1",
         "pickup": {"days": "0.458"}}
    t = tools.timeline(b)
    assert t["ready_date"] == "Wed 25 Nov 2026" and t["estimated_arrival"] == "Thu 26 Nov 2026"
    assert t["expected_stage_now"].startswith("booked") if _t.time() < datetime(2026, 11, 25, 9, tzinfo=timezone.utc).timestamp() else True


def test_a_consignment_of_lots_is_added_up_in_code():
    """Live round 9 (Sat 16:49): three lots, a total weight, weights per piece, dimensions per piece, net beside gross."""
    from app.forwarder import normalise
    q = lambda v, u, pp: {"value": v, "unit": u, "per_piece": pp}
    none = q(None, None, False)
    s = {"origin_airport": None, "pickup": {"postcode": "36627", "city": "Fulda"}, "destination_airport": "LOS",
         "cargo": {"commodity": "automotive sensors", "ready_date": "2026-11-29", "notes": None},
         "lots": [{"pieces": 4, "weight": q(730, "kg", False), "volume": q(1.68, "cbm", False), "dimensions": None},
                  {"pieces": 4, "weight": q(48, "kg", True), "volume": none,
                   "dimensions": {"length": 110, "width": 110, "height": 52, "unit": "cm"}},
                  {"pieces": 5, "weight": q(206, "kg", True), "volume": none,
                   "dimensions": {"length": 120, "width": 100, "height": 8, "unit": "cm"}}]}
    r = normalise(s, kit.world())
    assert r["pieces"] == 13 and D(r["weight_kg"]) == 1952 and r["volume_cbm"] == "4.6768"
    assert r["origin"] == "FRA" and r["pickup_zone"] == "36" and not r["missing"]
    # round 62: the lots sum to 9.3444 cbm; sent as 9.344 the portal priced 1560.448 kg of 1560.5148, and 5U did not
    # count that booking. The volume the portal and the sheets see is the one the chargeable weight comes from.
    s["lots"] = [{"pieces": 1, "weight": q(465, "kg", False), "volume": q(3.87, "cbm", False), "dimensions": None},
                 {"pieces": 3, "weight": q(160, "kg", True), "volume": none,
                  "dimensions": {"length": 100, "width": 60, "height": 46, "unit": "cm"}},
                 {"pieces": 3, "weight": q(59, "kg", True), "volume": none,
                  "dimensions": {"length": 110, "width": 110, "height": 128, "unit": "cm"}}]
    r = normalise(s, kit.world())
    assert r["volume_cbm"] == "9.3444" and D(r["chargeable_kg"]) == D("1560.5148")
    assert D(r["volume_cbm"]) * pricing.KG_PER_CBM == D(r["chargeable_kg"])
    from app.forwarder import kg_text
    assert kg_text(D("1560.5148")) == "1560.52" and kg_text(D("116.9")) == "116.9"  # never below the real weight


def test_durations_are_converted_by_code():
    """Live round 9: "Pickup time: 8 hours" was stored as 8 days by the reader, and the 50/50 pick went wrong."""
    assert language.days(8, "hours") == D("0.333") and language.days(4, "days") == 4 and language.days(29, "Hours") == D("1.208")
    # with the right hours, the 50/50 ratio rule picks 5U's trucker in round 9 too (Domblick, 361.24 EUR, 8 h)
    t = lambda rows: [Offer("pickup", n, D(p), language.days(h, "hours"), "email") for n, p, h in rows]
    r9 = t([("Vogelsberg Haulage", "194.64", 29), ("Domblick Kurierdienst", "361.24", 8), ("Bodenseefracht", "429.80", 6)])
    assert pricing.balanced(r9, "ratio").carrier == "Domblick Kurierdienst"


def test_every_pickup_zone_has_a_postcode_of_its_own_town():
    """Truckers answer only a request with a 5-digit postcode (live probe Sat 18:14); a town the customer names is
    asked with its zone's postcode."""
    zones = kit.world().zones
    assert set(kit.ZONE_POSTCODE) == set(zones)
    assert all(len(p) == 5 and p.startswith(z) for z, p in kit.ZONE_POSTCODE.items())


def test_an_amount_read_from_a_mail_must_be_in_the_mail():
    """Live Sat 18:27: Rheinufer wrote '94.08 EUR', the bid reader returned 9408."""
    from app.forwarder import amounts_in, read_in_mail
    body = "Our total price for pickup in Stuttgart and delivery to STR Airport is 94.08 EUR. Pickup time: 28 hours"
    assert read_in_mail({"available": True, "total": 94.08}, body)
    assert not read_in_mail({"available": True, "total": 9408}, body)
    assert {D("1234.50"), D("3.71"), D("94.08")} <= amounts_in("EUR 1,234.50 or 1.234,50; 3,71 per kg; 94.08")
    assert read_in_mail({"available": False, "total": None}, "we do not serve this lane")
    assert read_in_mail({"available": True, "total": None, "rate_per_kg": 3.71}, "rate EUR 3,71/kg")
    assert D("1234.50") in amounts_in("total EUR 1 234,50 all-in")


def test_one_schedule_for_quote_and_tracking():
    """Ready 28 Nov (09:00), pickup 19 h, 3 days in the air: leaves Sun 29 Nov, arrives Wed 2 Dec. The quote's option
    and the tracking timeline use the same function, so they tell the customer the same dates."""
    from datetime import datetime, timezone
    booked = datetime(2026, 11, 21, 17, 0, tzinfo=timezone.utc)
    _, leaves, arrives = pricing.schedule("2026-11-28", 19, D(3), booked)
    assert leaves.strftime(pricing.DATE) == "Sun 29 Nov 2026" and arrives.strftime(pricing.DATE) == "Wed 02 Dec 2026"
    from app.tools import timeline
    t = timeline({"booked_at": booked.timestamp(), "ready_date": "2026-11-28", "transit_days": "3",
                  "pickup": {"days": str(D(19) / 24)}})
    assert (t["estimated_departure"], t["estimated_arrival"]) == ("Sun 29 Nov 2026", "Wed 02 Dec 2026")


def test_an_offer_without_a_readable_time_cannot_win_on_speed():
    """Round 69: the trucker whose mail said "seven hours" was read without a time, stored as 0 days, and the 50/50
    pick took it for the fastest: 3602.11 instead of 3544.41 EUR. An unknown time counts as the slowest on offer."""
    from decimal import Decimal
    from app import pricing
    from app.pricing import Offer
    right = Offer("pickup", "Bodenseefracht", Decimal("119.01"), Decimal("1.25"), "email")
    fast = Offer("pickup", "Hansekogge", Decimal("245.02"), Decimal("0.958"), "email")
    unread = Offer("pickup", "Elbkante", Decimal("176.71"), Decimal(0), "email", extra={"time_unknown": True})
    assert pricing.balanced([right, fast, unread], "ratio").carrier == "Elbkante"          # what happened: 0 days wins
    seen = pricing.unknown_times_last([right, fast, unread])
    assert pricing.balanced(seen, "ratio").carrier == "Bodenseefracht"                      # round 2's scored pick again
    assert pricing.pick(seen, "fastest").carrier == "Hansekogge" and pricing.pick(seen, "cheapest").carrier == "Bodenseefracht"
    assert next(o for o in seen if o.carrier == "Elbkante").days == Decimal("1.25")
    alone = [unread, Offer("pickup", "X", Decimal("90"), Decimal(0), "email", extra={"time_unknown": True})]
    assert pricing.unknown_times_last(alone) == alone and pricing.balanced(alone, "ratio").carrier == "X"
