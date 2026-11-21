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
    q = pricing.quote(air, pick, "cheapest", True)
    assert q["total"] == "1050.00" and q["air"]["rate_id"] == "R-1" and q["pickup"]["carrier"] == "T2"
    assert pricing.quote(air, [], "cheapest", True) is None


def test_units():
    assert language.weight_kg({"value": 1000, "unit": "lb", "per_piece": False}, None) == D("453.59237")
    assert language.weight_kg({"value": 50, "unit": "kg", "per_piece": True}, 4) == 200
    dims = [{"count": 2, "length": 120, "width": 80, "height": 100, "unit": "cm"}]
    assert language.volume_cbm({"value": None, "unit": None, "per_piece": False}, dims, 2) == D("1.92")


def test_pickup_city_maps_to_zone():
    from app.forwarder import normalise
    p = {"pieces": 1, "weight": {"value": 100, "unit": "kg", "per_piece": False}, "volume": None, "dimensions": [],
         "pickup": {"postcode": None, "city": "Darmstadt"}, "origin_airport": None, "destination_airport": "JFK",
         "cargo": {"commodity": None, "ready_date": None, "notes": None}}
    r = normalise(p, kit.world())
    assert r["pickup_zone"] == "64" and r["origin"] == "FRA" and not r["missing"]


def test_live_bid_beats_stale_sheet():
    sheet = Offer("air", "Yellowtail Air Freight", D(800), D(4), "sheet")
    mail = Offer("air", "Yellowtail Air Freight", D(850), D(4), "email", "R-1")
    only_sheet = Offer("air", "Orion Cargo Air", D(900), D(2), "sheet")
    best = {o.carrier: o for o in pricing.best_by_carrier([sheet, mail, only_sheet])}
    assert best["Yellowtail Air Freight"].total == 850 and best["Orion Cargo Air"].total == 900


# ---- pick rules (docs/research/pricing.md) -------------------------------------------------------------------

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
    # defaults (behaviour so far): the trucker follows what the customer asked for
    assert q("cheapest")["total"] == "788.60" and q("cheapest")["pickup"]["carrier"] == "Bodenseefracht"
    assert q("fastest")["total"] == "1077.40" and q("fastest")["pickup"]["carrier"] == "Taunusfracht"
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
