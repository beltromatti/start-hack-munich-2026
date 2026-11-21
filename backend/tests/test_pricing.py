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
