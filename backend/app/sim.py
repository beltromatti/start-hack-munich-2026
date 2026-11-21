"""Realistic deals through the forwarder agent with the real model and the fake 5U.

    LLM_TARGET=openai DB_PATH=:memory: uv run python -m app.sim
LLM_TARGET=openai calls OpenAI directly with OPENAI_API_KEY: never counts as scored gateway spend.
"""
import sqlite3
import sys
import time

from . import kit, store
from .fake5u import FakeFiveU
from .forwarder import Forwarder

MAILS = [
    ("anna.becker@kraemer-maschinen.de", "Angebot Luftfracht nach Chicago",
     "Hallo,\n\nwir brauchen ein Angebot für 2 Kisten Ersatzteile, zusammen 320 kg, 1,5 cbm, von Frankfurt nach "
     "Chicago (ORD). Bitte das günstigste Angebot.\n\nViele Grüße\nAnna Becker\nKrämer Maschinenbau GmbH"),
    ("j.ortiz@lumentech.example", "Urgent: samples to Delhi",
     "Hi team,\n\nwe need to get 3 cartons of samples to New Delhi asap, fastest option please. Each carton is "
     "60x40x40 cm and weighs 35 kg. Pickup from our office at Hohenzollernring 12, 50672 Köln.\n\nThanks!\nJavier"),
    ("ops@bergwerk-tools.example", "RFQ MUC-JFK",
     "Please quote MUC to JFK, 1 pallet 120x80x150 cm, 410 kg, general cargo, ready Monday.\nRegards, Tom"),
    ("lea@kleinhandel.example", "Quote please", "Hi, can you send me a price for 80 kg to Kathmandu? Lea"),
    ("mike@freightbuyer.example", "price", "how much for a shipment to Sydney? thanks"),
]


def wait_idle(f: Forwarder, seconds: float) -> None:
    t = time.time()
    while time.time() - t < seconds:
        f.tick()
        busy = [k for k in f.inflight if k.startswith("thread:")]
        if not store.unhandled() and not busy:
            return
        time.sleep(0.5)


def main() -> None:
    store.use_connection(sqlite3.connect(":memory:", check_same_thread=False))
    api = FakeFiveU()
    kit.load(api)
    f = Forwarder(api)
    mails = MAILS[: int(sys.argv[1])] if len(sys.argv) > 1 else MAILS
    first = None
    for sender, subject, body in mails:
        m = api.customer(sender, subject, body)
        first = first or m
    t0 = time.time()
    wait_idle(f, 150)
    print(f"--- all requests handled in {time.time() - t0:.0f}s")
    quote = next((m for m in api.outbox if m["to"] == MAILS[0][0]), None)
    if quote:
        api.customer(MAILS[0][0], "Re: " + MAILS[0][1], "Passt, bitte buchen.\n\nAnna Becker", in_reply_to=quote["id"])
        wait_idle(f, 90)
        b = store.get(f"booking-{first['id']}")
        ref = (b or {}).get("data", {}).get("booking_reference") or (b or {}).get("data", {}).get("team_reference")
        api.customer("tracking@hackloop.mail", f"Status request {ref}",
                     f"Hello, could you tell me the current status and expected arrival of shipment {ref}? Thanks")
        wait_idle(f, 90)
    for r in sorted(store.records("deal"), key=lambda r: r["id"]):
        d = r["data"]
        print(f"\n=== {r['id']} {r['status']} quote={(d.get('quote') or {}).get('amount')} "
              f"in {(d.get('quote') or {}).get('response_seconds')}s req={d.get('request')}")
        for m in store.thread(d["root"]):
            if m["direction"] == "out":
                print(f"--- to {m['recipient']}:\n{m['body']}")
    for m in api.outbox:
        if m["to"] == "tracking@hackloop.mail":
            print(f"\n=== tracking answer:\n{m['body']}")
    print("\nusage", store.usage())
    for r in store.records("deal"):
        print(r["id"], store.usage(r["id"]))
    for e in store.events():
        if e["kind"] == "error":
            print("ERROR", e["summary"])


if __name__ == "__main__":
    main()
