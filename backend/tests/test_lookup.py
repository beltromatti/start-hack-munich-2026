"""The crm tool finds the right booking from what a customer says, also among many similar deals.

The cases are the ones the old substring count lost at 98 deals (Sat 21 Nov probe): a reference that is the prefix
of another, the weight in tonnes, a city instead of a code, a date as "25 Nov", one customer on one lane twice.
The model translates the words into fields (that is its job); these tests check the comparison the code does.
"""
from app import lookup, store, tools

FIRST = 1795273200.0  # 2026-11-21 13:00 UTC


def deal(n, customer, origin, dest, kg, ready, bk, sm, airline="Meridian"):
    req = {"origin": origin, "destination": dest, "weight_kg": str(kg), "ready_date": ready}
    b = {"booking_reference": bk, "team_reference": sm, "airline": airline, "route": f"{origin}-{dest}",
         "transit_days": "2", "status": "confirmed", "booked_at": FIRST + n, "ready_date": ready}
    store.put(f"deal-{n}", "deal", "booked", {"root": n, "customer": customer, "request": req, "booking": b})
    store.put(f"booking-{n}", "booking", "confirmed", b)


def world():
    deal(12, "rheintal-praezision@hackloop.mail", "CGN", "EZE", 410, "2026-11-24", "BK-AAA111", "SM-12")
    deal(123, "rheintal-praezision@hackloop.mail", "CGN", "EZE", 1620, "2026-11-25", "BK-BBB222", "SM-123")
    deal(5, "lindqvist-medtech@hackloop.mail", "CGN", "ORD", 676, "2026-11-23", "BK-CCC333", "SM-5")
    deal(6, "nordwind-logistik@hackloop.mail", "FRA", "ORD", 676, "2026-11-26", "BK-DDD444", "SM-6")
    for n in range(200, 260):  # the overnight register: many deals of other customers, same lanes and weights
        deal(n, f"customer-{n}@hackloop.mail", "CGN", ["EZE", "ORD", "DEL"][n % 3], 400 + n, "2026-11-25",
             f"BK-X{n}", f"SM-{n}")


DESK = tools.Ctx(None, "session-t", "deal-t", 0, "tracking", None)  # the tracking desk sees every customer


def first(**kw):
    return tools.crm(DESK, kw.pop("query", ""), **kw)["matches"][0]


def test_a_reference_is_a_whole_word_sm_12_is_not_sm_123():
    world()
    assert first(reference="SM-12")["deal_id"] == "deal-12"
    assert first(reference="SM-123")["deal_id"] == "deal-123"
    assert first(reference="BBB222")["deal_id"] == "deal-123"   # the code without its BK- prefix


def test_weight_in_tonnes_becomes_kg_and_counts_within_five_percent():
    world()  # "the 1.6 t shipment to Buenos Aires": the model writes 1600 and EZE
    m = first(customer="Rheintal Präzision", destination="EZE", weight_kg=1600)
    assert m["deal_id"] == "deal-123" and "weight (within 5 %)" in m["matched"]


def test_same_customer_same_lane_twice_the_date_tells_them_apart():
    world()  # "our shipment to Argentina ready on 24 Nov"
    m = first(customer="rheintal-praezision@hackloop.mail", destination="EZE", ready_date="2026-11-24")
    assert m["deal_id"] == "deal-12" and "ready_date" in m["matched"]


def test_same_weight_other_customer_is_not_confused():
    world()  # Lindqvist and Nordwind both shipped 676 kg to ORD
    m = first(customer="Lindqvist Medtech", destination="ORD", weight_kg=676)
    assert m["deal_id"] == "deal-5"
    assert "customer" in m["matched"] and m["differs"] == []


def test_a_typo_in_the_company_still_finds_it():
    world()
    assert first(customer="Lindqvst Medtec", destination="ORD")["deal_id"] == "deal-5"


def test_equal_fits_say_so():
    world()  # customer and lane only: both Rheintal deals fit
    out = tools.crm(DESK, "", customer="Rheintal", destination="EZE")
    assert {m["deal_id"] for m in out["matches"][:2]} == {"deal-12", "deal-123"}
    assert out["note"].startswith("2 deals fit equally")


def test_no_fields_gives_the_latest_deals():
    world()
    out = tools.crm(DESK, "")
    assert out["total_matches"] == 64 and len(out["matches"]) == 10


def test_a_returning_customer_brings_their_last_shipments_into_the_quote():
    world()
    lines = lookup.history("Rheintal-Praezision@hackloop.mail", exclude="deal-123")
    assert len(lines) == 1 and "CGN-EZE (Buenos Aires) 410 kg, booked Meridian, " in lines[0]
    assert lookup.history("new-customer@hackloop.mail") == []


def test_history_says_where_the_shipment_stands_and_leaves_out_what_we_did_not_book():
    """Offline, Sat 21 Nov: with "arrives <date>" alone the model wrote "hope it arrived well" for goods that were
    not collected yet, and a request we never quoted came back as "after your Riyadh request"."""
    deal(1, "weidner@hackloop.mail", "CGN", "DFW", 85, "2026-10-01", "BK-OLD00001", "SM-1")
    old = store.get("deal-1")["data"]
    old["booking"]["booked_at"] = FIRST - 60 * 86400                                           # flown weeks ago
    store.put("deal-1", "deal", "booked", old)
    deal(2, "weidner@hackloop.mail", "DUS", "ATL", 1754, "2999-01-01", "BK-NEW00002", "SM-2")  # not ready yet
    store.put("deal-3", "deal", "quoted", {"root": 3, "customer": "weidner@hackloop.mail", "quote": {"amount": "1.00"},
                                           "request": {"origin": "FRA", "destination": "RUH", "weight_kg": "50"}})
    lines = lookup.history("weidner@hackloop.mail")
    assert len(lines) == 2 and not any("RUH" in x for x in lines)
    assert "DUS-ATL (Atlanta)" in lines[0] and "not flown yet, arrives " in lines[0]
    assert "CGN-DFW (Dallas)" in lines[1] and ", arrived " in lines[1]


def test_history_is_cheap_on_a_full_night():
    import time
    for n in range(1000, 1600):  # 600 deals, more than the register's default page of 500
        deal(n, "busy@hackloop.mail" if n == 1000 else f"c{n}@hackloop.mail", "FRA", "SGN", 300, "2026-11-22",
             f"BK-Y{n}", f"SM-{n}")
    t = time.perf_counter()
    lines = lookup.history("busy@hackloop.mail")
    assert lines and (time.perf_counter() - t) < 0.5            # the oldest deal is still seen
    assert len(" ".join(lines)) < 300                            # a few dozen tokens in the tool result
