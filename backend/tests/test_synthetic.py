"""The synthetic answer key must be right, or it teaches the pipeline wrong prices."""
import json
from decimal import Decimal

from synthetic.build import HERE, chargeable, load_kit, sheet_price
from synthetic.mails import MAILS

TARIFFS, CARRIERS, ZONES = load_kit()


def lane(airline, origin, dest):
    return next(l for l in TARIFFS["lanes"]
                if l["airline"].startswith(airline) and l["origin"] == origin and l["destination"] == dest)


def test_299_kg_is_billed_as_300():
    # Wayzata CGN-DEL: 299 x 3.02 + 299 x 1.41 = 1324.57, but 300 x 2.38 + 300 x 1.41 = 1137.00
    p = sheet_price(lane("Wayzata", "CGN", "DEL"), Decimal("299"))
    assert p["billed_kg"] == 300 and p["total_eur"] == Decimal("1137.00")


def test_volume_decides_the_weight():
    # 1.8 cbm x 167 = 300.6 kg > 120 kg. Yellowtail FRA-NBO: 300.6 x 2.18 + 300.6 x 1.10 = 985.97
    cw = chargeable(Decimal("120"), Decimal("1.8"))
    assert cw == Decimal("300.6")
    assert sheet_price(lane("Yellowtail", "FRA", "NBO"), cw)["total_eur"] == Decimal("985.97")


def test_lbs_just_under_a_break():
    # 1,100 lbs = 498.95 kg. Kestrel HAM-HKG: at 498.95 x (1.93 + 0.78) = 1352.15, at 500 x (1.66 + 0.78) = 1220.00
    p = sheet_price(lane("Kestrel", "HAM", "HKG"), Decimal("498.95"))
    assert p["billed_kg"] == 500 and p["total_eur"] == Decimal("1220.00")


def test_minimum_charge_applies_to_freight_only():
    l = lane("Wayzata", "CGN", "DEL")
    p = sheet_price(l, Decimal("1"))
    assert p["total_eur"] == Decimal("87.98") + Decimal("1.41")


def test_answer_key_covers_every_mail():
    expected = json.loads((HERE / "expected.json").read_text())
    assert set(expected) == {m["id"] for m in MAILS}
    for m in MAILS:
        e = expected[m["id"]]
        if e.get("action") == "quote":
            q = e["expected_quote"]
            assert q["currency"] == "EUR" and Decimal(q["total_eur"]) > 0
            assert Decimal(q["total_eur"]) == min(Decimal(o["total_eur"]) for o in e["offers"]) \
                or e["preference"] == "fastest"
        if m.get("thread"):
            assert m["thread"] in expected


def test_pickup_postcodes_map_to_the_origin_airport():
    expected = json.loads((HERE / "expected.json").read_text())
    for e in expected.values():
        if e.get("pickup_postcode"):
            assert e["pickup_airport"] == e["origin"] and len(e["truckers_to_ask"]) >= 2
