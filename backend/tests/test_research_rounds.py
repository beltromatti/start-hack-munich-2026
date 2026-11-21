"""The read-only round log: groups mailbox mail per customer request and names the trucker per rule."""
from research import rounds


def mail(i, frm, subject, body, re=None, refs=None, at="2026-11-21T15:00:00+00:00"):
    return {"id": i, "from": frm, "subject": subject, "body": body, "in_reply_to": re, "references": refs or [],
            "received_at": at, "attachments": []}


def test_bids_are_attached_to_the_request_and_each_rule_names_its_trucker():
    mails = [
        mail(1, "anna@acme.hackloop.mail", "RFQ", "320 kg from 60311 Frankfurt to Chicago, fastest please"),
        mail(5, "bodenseefracht@hackloop.mail", "Re: Pickup", "Total: 88.60 EUR.\nPickup within 26 hours. TRK-82.",
             re=2, at="2026-11-21T15:00:35+00:00"),
        mail(6, "westfalenroute@hackloop.mail", "Re: Pickup", "price is 96.80 EUR.\nPickup within: 23 hours TRK-79",
             re=3, at="2026-11-21T15:00:35+00:00"),
        mail(7, "taunusfracht@hackloop.mail", "Re: Pickup", "is 177.40 EUR. We can pick up within 3 hours. TRK-83",
             re=4, at="2026-11-21T15:02:10+00:00"),
        mail(8, "yellowtail-air-freight@hackloop.mail", "Re: Rate request", "rate is 828.80 EUR.\nTransit time: 4 days"
             "\nPlease quote reference R-MlgBHI1drqcnW--P when booking.", re=9, at="2026-11-21T15:00:36+00:00"),
        mail(9, "wayzata-air-cargo@hackloop.mail", "Wayzata tariff December 2026", "New tariff attached."),
        mail(10, "anna@acme.hackloop.mail", "Re: RFQ", "We accept, please book.", re=11, refs=[1, 11]),
    ]
    (r,) = rounds.rounds(mails)
    assert [b["carrier"] for b in r["bids"]] == ["Bodenseefracht", "Westfalenroute", "Taunusfracht",
                                                 "Yellowtail Air Freight"]
    assert r["bids"][3]["total"] == "828.80" and r["bids"][3]["days"] == "4" and r["bids"][0]["hours"] == "26"
    assert len(r["follow_ups"]) == 1
    picks = {k: o.carrier for k, o in rounds.trucker_picks(r["bids"]).items()}
    assert picks == {"cheapest": "Bodenseefracht", "fastest": "Taunusfracht", "minmax": "Westfalenroute",
                     "ratio": "Taunusfracht"}
    sig = " | ".join(rounds.signals(r))
    assert "SLOW" in sig and "NOTICE: wayzata-air-cargo@hackloop.mail" in sig and "CURRENCY" not in sig
