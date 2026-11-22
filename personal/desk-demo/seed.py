"""A small real register for looking at the desk against the real API: the tests' scripted model and the fake 5U
run a few deals end to end (quote, booking, a question), then one deal is marked as waiting for a person.
No network, no key.   cd backend && DB_PATH=/tmp/x.db uv run python ../personal/desk-demo/seed.py"""
import os, sqlite3, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
import conftest
from test_flow import Sync, run, to
from app import kit, llm, store
from app.fake5u import FakeFiveU

store.use_connection(sqlite3.connect(os.environ["DB_PATH"], check_same_thread=False))
llm.use_fake(conftest.fake_llm)
llm.use_fake_turn(conftest.fake_agent)
api = FakeFiveU()
kit.load(api)
f = Sync(api)

anna = api.customer("anna@acme.example", "Quote FRA to ORD", "Hi, please quote 320 kg, 1.5 cbm, FRA to ORD, cheapest.")
run(f)
q = to(api, "anna@acme.example")
api.customer("anna@acme.example", "Re: Quote FRA to ORD", "Great, go ahead and book it.", in_reply_to=q[0]["id"])
run(f); run(f)
api.customer("anna@acme.example", "Quote FRA to JFK", "Hi, please quote 150 kg, 0.8 cbm, FRA to JFK, fastest.")
run(f)
bob = api.customer("bob@beta.example", "Price MUC to DXB", "Hello, 212 kg, 1.9 cbm, MUC to DXB, cheapest please.")
run(f)
api.customer("carla@gamma.example", "Request", "Hello, we have two boxes from HAM to SIN, cheapest.")
run(f)
dana = api.customer("dana@delta.example", "Quote HAM to HKG", "Hi, please quote 600 kg, 3 cbm, HAM to HKG, fastest.")
run(f)

def flag_note(text, flag):
    def f(r):
        d = r["data"]
        d["notes"] = d.get("notes", []) + [{"at": time.time(), "text": text, "flag": flag}]
        d["flag"] = flag
        return r["status"], d
    return f
store.update(f"deal-{bob['id']}", flag_note("The packing list says 1.92 cbm and the mail says 2.78 cbm. I priced from the packing list and said so in the quote.", "yellow"))
store.update(f"deal-{dana['id']}", flag_note("The sender address is one character off the one we know. I changed nothing and asked for the booking reference.", "red"))
print("deals:", [(r["id"], r["status"]) for r in store.records("deal")])
