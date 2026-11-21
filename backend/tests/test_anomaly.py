"""Anomaly watch: each market change from docs/research/watcher.md raises its signal, the baseline raises none."""
from app import anomaly, store

AIR = "aurelia-air-cargo@hackloop.mail"


def mail(id_, direction, sender, body, at, reply=None, files=None, subject="Re: rate request"):
    return {"id": id_, "direction": direction, "sender": sender, "recipient": "x", "subject": subject, "body": body,
            "in_reply_to": reply, "root": 1, "received_at": at, "attachments": files or [], "kind": None}


ASK = mail(1, "out", "start-milan@hackloop.mail", "Please quote FRA-ORD 320 kg", "2026-11-21T15:00:00+00:00")


def keys(mails, events=(), board=None):
    return {s["key"] for s in anomaly.signals(mails, list(events), board)}


def test_baseline_is_quiet():
    ok = mail(2, "in", AIR, "Total 1234.50 EUR, transit 3 days, ref R-1", "2026-11-21T15:00:31+00:00", reply=1)
    assert keys([ASK, ok], board={"requests": [{"round": 1, "verdict": "accepted"}]}) == set()


def test_each_change_raises_its_signal():
    slow = mail(2, "in", AIR, "Total 1234.50 EUR", "2026-11-21T15:01:40+00:00", reply=1)
    usd = mail(3, "in", AIR, "Total USD 1,400.00", "2026-11-21T15:00:30+00:00", reply=1)
    ask = mail(4, "in", AIR, "To quote we need the total weight in kg.", "2026-11-21T15:00:30+00:00", reply=1)
    sheet = mail(5, "in", AIR, "New tariff valid from 1 Dec attached.", "2026-11-21T15:10:00+00:00",
                 files=[{"filename": "dec.xlsx"}], subject="Tariff December")
    events = [{"id": 9, "kind": "error", "agent": "bids", "summary": "portal FRA-ORD: 503 use the rate desk"},
              {"id": 10, "kind": "llm", "agent": "forwarder", "summary": "gpt-6-luna [turn] 3.1s DIRECT (gateway down)"}]
    board = {"requests": [{"round_no": 7, "verdict": "rejected", "reason": "price above market"},
                          {"round_no": 8, "verdict": "accepted", "sent_at": "2026-11-21T16:00:00+00:00",
                           "answered_at": "2026-11-21T16:02:30+00:00"}]}
    got = keys([ASK, slow, usd, ask, sheet], events, board)
    assert got == {"slow", "currency:USD", "askback", f"tariff:{AIR}", f"validity:{AIR}",
                   "http:503:bids", "gateway-down", "board:price-above-market", "late-answer"}


def test_customer_reply_naming_a_problem_is_a_signal():
    calm = mail(6, "in", "anna@acme.de", "Thanks, please book it.", "2026-11-21T15:05:00+00:00", reply=1)
    strike = mail(7, "in", "luca@moda.it", "Attenzione: sciopero a MXP, ritardi su tutte le spedizioni.",
                  "2026-11-21T15:06:00+00:00", reply=1)
    assert keys([calm]) == set()
    [s] = anomaly.signals([calm, strike], [], None)
    assert s["key"] == "customer:1" and s["change"] == "15" and "sciopero" in s["what"]


def deal(i, sheet, live, carrier="Elbflug"):
    return {"id": f"deal-{i}", "updated_at": i, "data": {"offers": [
        {"leg": "air", "carrier": carrier, "total": str(sheet), "source": "sheet"},
        {"leg": "air", "carrier": carrier, "total": str(live), "source": "portal"}]}}


def test_price_jump_against_the_carriers_own_history():
    steady = [deal(i, 1000, 1010 + i) for i in range(5)]  # live about 1 % over sheet, every deal
    assert anomaly.price_shocks(steady) == []
    [s] = anomaly.price_shocks(steady + [deal(9, 1000, 1180)])  # +18 %: a new tariff
    assert s["deal"] == "deal-9" and s["z"] >= 3
    [first] = anomaly.price_shocks([deal(1, 1000, 1300)])  # first live price 30 % off: sheet stale
    assert first["z"] is None and first["ratio"] == 1.3


def test_check_opens_once_and_reopens_on_new_evidence():
    store.save_mail({"id": 1, "from": "start-milan@hackloop.mail", "to": AIR, "subject": "rate", "body": "q",
                     "received_at": "2026-11-21T15:00:00+00:00"}, "out")
    store.save_mail({"id": 2, "from": AIR, "to": "x", "subject": "Re", "body": "Total USD 1,400.00",
                     "in_reply_to": 1, "references": [1], "received_at": "2026-11-21T15:00:30+00:00"}, "in")
    assert [i["id"] for i in anomaly.check(diagnose_new=False)] == ["incident-currency-USD"]
    assert anomaly.check(diagnose_new=False) == []  # open already: no second alert, no second model call
    anomaly.close("currency:USD")
    assert anomaly.check(diagnose_new=False) == []  # closed and nothing new
    store.save_mail({"id": 3, "from": AIR, "to": "x", "subject": "Re", "body": "Total USD 900.00",
                     "in_reply_to": 1, "references": [1], "received_at": "2026-11-21T15:00:40+00:00"}, "in")
    assert [i["id"] for i in anomaly.check(diagnose_new=False)] == ["incident-currency-USD"]
    assert "Total USD 900.00" in anomaly.brief(store.records("incident", "open"))


def test_diagnosis_never_goes_through_the_scored_gateway(monkeypatch):
    """Production without a direct OpenAI key: the diagnosis is skipped, the gateway client is never touched."""
    from dataclasses import replace
    from app import llm
    monkeypatch.setattr(anomaly, "settings", replace(anomaly.settings, llm_base_url="https://gateway.example/v1"))
    monkeypatch.setattr(llm, "direct", lambda: None)
    monkeypatch.setattr(llm, "client", lambda: (_ for _ in ()).throw(AssertionError("gateway used")))
    assert "skipped" in anomaly.diagnose({"key": "x", "change": "7", "what": "y", "evidence": []})
