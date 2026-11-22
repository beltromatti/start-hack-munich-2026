"""Accounts: who may open the desk. Records in the register (type "account"), a salted PBKDF2 hash of the
password, and a signed session cookie. The forwarder never reads them: they guard the UI and its API.

While the register holds no account (a laptop, the tests) the desk stays open, as before. The first account
closes it: from then on every /api call needs a signed-in person, except /api/health and the login itself.

    python -m app.accounts add mattia "Mattia Beltrami"     # asks for the password, or --generate
    python -m app.accounts list
"""
import argparse
import getpass
import hashlib
import hmac
import secrets
import sys
import time

from . import store

COOKIE = "desk_session"
DAYS = 14
_ITER = 310_000
_FAILS: dict[str, list[float]] = {}  # address -> times of failed logins, for the brake


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER).hex()


def _id(username: str) -> str:
    return "account-" + username.strip().lower()


def public(r: dict) -> dict:
    d = r["data"]
    return {"username": d["username"], "name": d["name"], "role": d.get("role", "ops")}


def add(username: str, password: str, name: str, role: str = "ops") -> dict:
    """Creates the account, or sets a new password and name on an existing one."""
    username = username.strip().lower()
    if not username.isidentifier() or len(password) < 10:
        raise ValueError("a username of letters, digits or _, and a password of at least 10 characters")
    salt = secrets.token_hex(16)
    store.put(_id(username), "account", "active", {"username": username, "name": name.strip() or username,
                                                     "role": role, "salt": salt, "hash": _hash(password, salt),
                                                     "created": time.time()})
    store.log("desk", "info", f"account {username} set")
    return public(store.get(_id(username)))


def all_() -> list[dict]:
    return [public(r) for r in store.records("account", "active")]


def any_() -> bool:
    return bool(store.records("account", "active", limit=1))


def check(username: str, password: str) -> dict | None:
    r = store.get(_id(username or ""))
    if not r or r["status"] != "active":
        _hash(password or "", "even-timing")  # an unknown name costs as much as a wrong password
        return None
    d = r["data"]
    return public(r) if hmac.compare_digest(_hash(password or "", d["salt"]), d["hash"]) else None


def braked(address: str) -> bool:
    """Ten wrong passwords from one address in ten minutes, then a pause: guessing stays slow."""
    now = time.time()
    _FAILS[address] = [t for t in _FAILS.get(address, []) if now - t < 600]
    return len(_FAILS[address]) >= 10


def failed(address: str) -> None:
    _FAILS.setdefault(address, []).append(time.time())


def _secret() -> bytes:
    """The key that signs sessions: made once and kept in the register, so a restart keeps people signed in."""
    s = store.kv_get("session_secret")
    if not s:
        s = secrets.token_hex(32)
        store.kv_set("session_secret", s)
    return s.encode()


def token(username: str) -> str:
    body = f"{username}|{int(time.time() + DAYS * 86400)}|{secrets.token_hex(8)}"
    return body + "|" + hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()


def who(tok: str | None) -> dict | None:
    """The signed-in account behind a session cookie, or None (unsigned, expired, or the account is gone)."""
    try:
        username, until, nonce, sig = (tok or "").split("|")
    except ValueError:
        return None
    body = f"{username}|{until}|{nonce}"
    if not hmac.compare_digest(sig, hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()):
        return None
    if int(until) < time.time():
        return None
    r = store.get(_id(username))
    return public(r) if r and r["status"] == "active" else None


def _cli() -> None:
    p = argparse.ArgumentParser(prog="python -m app.accounts")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="create an account, or reset its password")
    a.add_argument("username")
    a.add_argument("name")
    a.add_argument("--role", default="ops", choices=["ops", "sales", "carriers"])
    a.add_argument("--generate", action="store_true", help="make a strong password and print it once")
    sub.add_parser("list")
    args = p.parse_args()
    store.conn()
    if args.cmd == "list":
        for x in all_():
            print(f"{x['username']}\t{x['name']}\t{x['role']}")
        return
    if args.generate:
        password = secrets.token_urlsafe(15)
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Again: "):
            sys.exit("The two passwords differ.")
    out = add(args.username, password, args.name, args.role)
    print(f"Account {out['username']} ({out['name']}) is set.")
    if args.generate:
        print(f"Password: {password}")


if __name__ == "__main__":
    _cli()
