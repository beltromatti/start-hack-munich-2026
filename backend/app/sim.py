"""Realistic customer mails through the whole pipeline with the real model and the fake 5U.

    LLM_TARGET=openai DB_PATH=:memory: uv run python -m app.sim
LLM_TARGET=openai calls OpenAI directly with OPENAI_API_KEY: never counts as scored gateway spend.
"""
import sqlite3
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


def main() -> None:
    store.use_connection(sqlite3.connect(":memory:", check_same_thread=False))
    api = FakeFiveU()
    kit.load(api)
    f = Forwarder(api)
    for sender, subject, body in MAILS:
        api.customer(sender, subject, body)
    t = time.time()
    while time.time() - t < 90:
        f.tick()
        if all(r["status"] not in ("pricing", "collecting", "quoting") for r in store.records("rfq")) \
                and len(store.records("rfq")) == len(MAILS):
            break
        time.sleep(0.5)
    time.sleep(2)
    for r in sorted(store.records("rfq"), key=lambda r: r["id"]):
        d = r["data"]
        print(f"\n=== {r['id']} {r['status']} {d.get('amount')} req={d['request']}")
        reply = [m for m in api.outbox if m["to"] == d["customer"]]
        print(reply[-1]["body"] if reply else "(no reply)")
    print("\nusage", store.usage())
    for e in store.events():
        if e["kind"] == "error":
            print("ERROR", e["summary"])


if __name__ == "__main__":
    main()
