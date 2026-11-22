"""The desk's sign-in: open while there is no account, closed by the first one, and nothing of the register
leaks to someone not signed in."""
from fastapi.testclient import TestClient

from app import accounts, store
from app.main import app


def test_no_account_keeps_the_desk_open():
    c = TestClient(app)
    assert c.get("/api/me").json() == {"account": None, "open": True}
    assert c.get("/api/deals").status_code == 200


def test_the_first_account_closes_every_api_but_health_and_login():
    accounts.add("mattia", "a long secret 123", "Mattia")
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    for path in ("/api/deals", "/api/board", "/api/accounts", "/api/sessions", "/api/me"):
        assert c.get(path).status_code == 401, path
    assert c.post("/api/sessions/session-1/message", json={"text": "hi"}).status_code == 401


def test_sign_in_with_the_right_password_only():
    accounts.add("mattia", "a long secret 123", "Mattia")
    c = TestClient(app)
    assert c.post("/api/login", json={"username": "mattia", "password": "wrong one"}).status_code == 401
    assert c.post("/api/login", json={"username": "nobody", "password": "a long secret 123"}).status_code == 401
    r = c.post("/api/login", json={"username": "Mattia", "password": "a long secret 123"})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/me").json()["account"] == {"username": "mattia", "name": "Mattia", "role": "ops"}
    assert c.get("/api/deals").status_code == 200
    c.post("/api/logout")
    assert c.get("/api/deals").status_code == 401


def test_a_forged_or_expired_cookie_is_refused():
    accounts.add("mattia", "a long secret 123", "Mattia")
    good = accounts.token("mattia")
    user, until, nonce, sig = good.split("|")
    assert accounts.who(good)["username"] == "mattia"
    assert accounts.who(f"admin|{until}|{nonce}|{sig}") is None
    assert accounts.who(f"{user}|{int(until) + 999}|{nonce}|{sig}") is None
    assert accounts.who("") is None


def test_the_password_is_never_stored():
    accounts.add("mattia", "a long secret 123", "Mattia")
    assert "a long secret 123" not in str(store.get("account-mattia"))


def test_guessing_is_braked():
    accounts.add("mattia", "a long secret 123", "Mattia")
    accounts._FAILS.clear()
    c = TestClient(app)
    codes = [c.post("/api/login", json={"username": "mattia", "password": f"guess {i}"}).status_code for i in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    accounts._FAILS.clear()


def test_a_message_is_recorded_under_the_signed_in_person():
    accounts.add("mattia", "a long secret 123", "Mattia Beltrami")
    c = TestClient(app)
    c.post("/api/login", json={"username": "mattia", "password": "a long secret 123"})
    seen = {}
    from app import agent
    real = agent.operator_message
    agent.operator_message = lambda sid, text, who: seen.update(who=who) or {"status": "idle", "data": {"root": 1}}
    try:
        c.post("/api/sessions/session-1/message", json={"text": "use Lufthansa", "who": "Sam"})
    finally:
        agent.operator_message = real
    assert seen["who"] == "Mattia Beltrami"


def test_this_machine_reads_freely_but_the_tunnel_does_not():
    """The monitor and scripts on the Mac call localhost:8000; the Cloudflare tunnel also arrives on loopback, with
    Cloudflare's headers, and must sign in."""
    accounts.add("mattia", "a long secret 123", "Mattia")
    here = TestClient(app, client=("127.0.0.1", 50000))
    assert here.get("/api/deals").status_code == 200
    assert here.get("/api/me").json() == {"account": None, "open": True}
    for h in ({"cf-ray": "8f00-MXP", "cf-connecting-ip": "203.0.113.9"}, {"x-forwarded-for": "203.0.113.9"}):
        assert here.get("/api/deals", headers=h).status_code == 401
        assert here.get("/api/me", headers=h).status_code == 401
    assert TestClient(app, client=("192.168.1.20", 50000)).get("/api/deals").status_code == 401


def test_a_kept_chart_belongs_to_its_person_and_is_computed_again():
    accounts.add("mattia", "a long secret 123", "Mattia")
    accounts.add("sam", "another long secret", "Sam")
    a, b = TestClient(app), TestClient(app)
    a.post("/api/login", json={"username": "mattia", "password": "a long secret 123"})
    b.post("/api/login", json={"username": "sam", "password": "another long secret"})
    pid = a.post("/api/pins", json={"spec": {"measure": "shipments", "group_by": "status", "kind": "bar"}}).json()["id"]
    assert [p["id"] for p in a.get("/api/pins").json()] == [pid] and a.get("/api/pins").json()[0]["kind"] == "bar"
    assert b.get("/api/pins").json() == [] and b.post(f"/api/pins/{pid}/remove").status_code == 404
    assert a.post("/api/pins", json={"spec": {"measure": "nonsense", "group_by": "status"}}).status_code == 400
    a.post(f"/api/pins/{pid}/remove")
    assert a.get("/api/pins").json() == []
