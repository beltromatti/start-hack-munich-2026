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
