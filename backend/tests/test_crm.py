"""The CRM projection reads the register and never writes: signatures, round points from board deltas, one case per
customer request with our quote and the carriers' answers."""
from app import crm, store

T0 = 1795276800  # 2026-11-21 16:00 Europe/Berlin


def iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


def mail(i, frm, to, subject, body, t, root=None, direction="in"):
    m = {"id": i, "from": frm, "to": to, "subject": subject, "body": body, "received_at": iso(t),
         "in_reply_to": root, "references": [root] if root else []}
    store.save_mail(m, direction, "backup", handled=True)


def snap(at, total, rounds, teams):
    me = {"team": "START Milan", "rank": 1, "total": total,
          "requests": [{"round_no": n, "sent_at": iso(T0), "verdict": v} for n, v in rounds]}
    pub = {"ranking": [{"name": k, "team": k, "total": v} for k, v in teams.items()]}
    store.put(f"board-{at}", "board", "snapshot", {"me": me, "public": pub, "at": at})


def test_signature_reads_name_title_company_and_skips_the_quoted_mail():
    body = ("Hello,\n\nplease quote 500 kg.\n\nViele Gruesse\nLena Huber\nHead of Logistics\nAlpenwerk GmbH\n\n"
            "-----Original Message-----\nFrom: someone\nBest regards\nOther Person")
    s = crm.signature(body)
    assert (s["person"], s["title"], s["company"]) == ("Lena Huber", "Head of Logistics", "Alpenwerk GmbH")


def test_round_points_come_from_a_delta_with_exactly_one_new_verdict():
    snap(T0 + 60, 100.0, [(1, "accepted")], {"start-milan": 100.0})
    snap(T0 + 120, 170.0, [(1, "accepted"), (2, "accepted")], {"start-milan": 170.0})
    snap(T0 + 180, 570.5, [(1, "accepted"), (2, "accepted")], {"start-milan": 570.5})  # an hourly batch
    p = crm.points_timeline()
    assert p["per_round"] == {2: 70.0}
    assert [b["delta"] for b in p["batches"]] == [400.5]
    assert [s["teams"]["start-milan"] for s in p["series"]] == [100.0, 170.0, 570.5]


def test_a_customer_request_becomes_one_case_with_our_quote_and_the_carriers_answers():
    snap(T0 - 10, 0.0, [], {"start-milan": 0.0})
    mail(1, "alpenwerk@hackloop.mail", "start-milan@hackloop.mail", "Air freight quote to JFK",
         "Please quote 500 kg, 2 cbm, cheapest.\n\nBest regards\nLena Huber\nAlpenwerk GmbH", T0)
    mail(2, "start-milan@hackloop.mail", "ratedesk@hackloop.mail", "Rate request MUC-JFK 500 kg", "Rate?", T0 + 3,
         direction="out")
    mail(3, "start-milan@hackloop.mail", "alpenwerk@hackloop.mail", "Re: Air freight quote to JFK",
         "Hello Lena,\n\nTotal: 1.234,50 EUR all-in\n\nGiulia", T0 + 40, root=1, direction="out")
    c = crm.cases()
    assert len(c) == 1
    assert c[0]["customer"] == "Alpenwerk GmbH" and c[0]["contact"] == "Lena Huber"
    assert c[0]["quoteTotal"] == 1234.5 and c[0]["quoteAt"] == 40 and not c[0]["askedBack"]
    assert crm.customers(c)[0]["n"] == 1


def test_traits_name_what_makes_a_request_harder():
    body = "Please quote to GRU. Pickup at our warehouse.\nLot 1: 4 drums\nI attached the packing list.\n\nKlaus"
    assert crm.traits("Air freight quote", body) == ["lots", "attachment", "no postcode"]
    assert crm.traits("Quote", "Pickup at 61391 Bad Homburg, earliest arrival?") == ["earliest arrival"]


def test_rows_give_one_flat_row_per_request_for_correlations():
    from app import crm
    cs = [{"start": 1795273200.0 + i * 360, "round": i + 1, "customer": "Weidner", "email": "w@x", "origin": "FRA",
           "destination": "SGN", "pickupZone": "60" if i else None, "weightKg": 300.0, "volumeCbm": 1.0,
           "chargeableKg": 300.0, "pieces": 2, "commodity": "toys", "readyDate": "2026-11-23", "wants": "cheapest",
           "traits": ["lots"], "bids": [{"total": 900.0, "kind": "airline", "declined": False},
                                        {"total": 120.0, "kind": "trucker", "declined": False}],
           "quoteTotal": 1020.0, "firstReplyAt": 30, "quoteAt": 30, "askedBack": False, "costUsd": 0.001,
           "verdict": "accepted", "reason": None, "booked": "BK-1", "points": 60.0, "pointsBy": {"cost": 39.0},
           "tracking": []} for i in range(2)]
    rs = crm.rows(cs)
    assert [r["nth_request_of_customer"] for r in rs] == [1, 2]
    assert rs[1]["door_to_port"] and rs[0]["cheapest_air_bid"] == 900.0 and rs[0]["points_cost"] == 39.0
    assert rs[0]["hour_utc"] == 15 and rs[0]["ready_in_days"] == 1.3
