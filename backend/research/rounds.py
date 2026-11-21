"""Round log: what 5U scored, next to what the mailbox shows. READ-ONLY (GET on board and mailbox only).

    cd backend && FIVEU_BASE_URL=... FIVEU_API_KEY=... uv run python -m research.rounds          # pull + print
    ... uv run python -m research.rounds --offline                                                # print only

Never sends mail, never calls the portal or the gateway. Raw data stays in backend/data/research/ (gitignored).
Per customer request it lists the bids that arrived for it and, for the pickup leg, which trucker each
candidate rule would take (cheapest / fastest / minmax / ratio), so a verdict on the board can be matched
to a rule. See docs/research/pricing.md.
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx

from app import kit, pricing
from app.pricing import Offer

DATA = Path(__file__).resolve().parents[1] / "data" / "research"
MAILS, BOARD, PUBLIC = DATA / "mailbox.json", DATA / "board-me.json", DATA / "board.json"
DESKS = {"ratedesk@hackloop.mail", "tracking@hackloop.mail"}
AMOUNT = re.compile(r"(\d[\d,]*\.\d{2})\s*(EUR|USD|GBP|CHF)")


def pull() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    http = httpx.Client(base_url=os.environ["FIVEU_BASE_URL"], headers={"X-API-Key": os.environ["FIVEU_API_KEY"]},
                        timeout=20)
    mails = json.loads(MAILS.read_text()) if MAILS.exists() else []
    since = max((m["id"] for m in mails), default=0)
    for _ in range(20):
        d = http.get("/v1/mailbox/messages", params={"since_id": since, "limit": 200}).json()
        mails += d["messages"]
        if not d["messages"] or d["next_since_id"] == since:
            break
        since = d["next_since_id"]
    MAILS.write_text(json.dumps(mails, indent=1, ensure_ascii=False))
    me = http.get("/v1/board/me").json()
    BOARD.write_text(json.dumps(me, indent=1, ensure_ascii=False))
    (DATA / f"board-me-{time.strftime('%H%M')}.json").write_text(json.dumps(me, ensure_ascii=False))
    PUBLIC.write_text(json.dumps(http.get("/v1/board").json(), indent=1, ensure_ascii=False))


def ts(m: dict) -> float:
    return datetime.fromisoformat(m["received_at"]).timestamp()


def bid(m: dict, carrier: kit.Carrier) -> dict:
    """A carrier reply read by pattern (the live formats are fixed enough for a log; production uses the model)."""
    body = m["body"]
    amount = AMOUNT.search(body)
    hours = re.search(r"(\d+(?:\.\d+)?)\s*hours?", body)
    days = re.search(r"(\d+(?:\.\d+)?)\s*days?", body)
    ref = re.search(r"\b(R-[\w-]+|TRK-\d+)", body)
    return {"mail": m["id"], "carrier": carrier.name, "kind": carrier.kind, "subject": m["subject"],
            "total": amount.group(1).replace(",", "") if amount else None, "currency": amount.group(2) if amount else None,
            "hours": hours.group(1) if hours and carrier.kind == "trucker" else None,
            "days": days.group(1) if days and carrier.kind == "airline" else None, "ref": ref.group(1) if ref else None,
            "no": "do not serve" in body or "To quote we need" in body, "at": m["received_at"], "re": m.get("in_reply_to")}


def rounds(mails: list[dict]) -> list[dict]:
    """One entry per customer thread; carrier replies are attached to the newest request before them."""
    w = kit.world()
    out: list[dict] = []
    by_root: dict[int, dict] = {}
    for m in sorted(mails, key=lambda x: x["id"]):
        sender = m["from"].lower()
        c = w.carrier_by_email(sender)
        root = (m.get("references") or [m["id"]])[0]
        if c is None and sender not in DESKS:
            if root in by_root:
                by_root[root]["follow_ups"].append(m)
            else:
                by_root[root] = r = {"root": root, "rfq": m, "bids": [], "follow_ups": [], "desk": []}
                out.append(r)
        elif out and c is not None:
            out[-1]["bids"].append(bid(m, c))
        elif out:
            out[-1]["desk"].append(m)
    return out


def trucker_picks(bids: list[dict]) -> dict:
    offers = [Offer("pickup", b["carrier"], Decimal(b["total"]), Decimal(b["hours"]) / 24, "email")
              for b in bids if b["kind"] == "trucker" and b["total"] and b["hours"]]
    offers = pricing.best_by_carrier(offers)
    if not offers:
        return {}
    return {"cheapest": pricing.pick(offers, "cheapest"), "fastest": pricing.pick(offers, "fastest"),
            "minmax": pricing.balanced(offers, "minmax"), "ratio": pricing.balanced(offers, "ratio")}


def show() -> None:
    kit.load(None)
    mails = json.loads(MAILS.read_text()) if MAILS.exists() else []
    me = json.loads(BOARD.read_text()) if BOARD.exists() else {}
    print(f"board/me: rank {me.get('rank')} total {me.get('total')} requests {len(me.get('requests', []))} "
          f"bookings {len(me.get('bookings', []))}")
    for r in me.get("requests", []):
        print("  ", json.dumps(r, ensure_ascii=False))
    for r in rounds(mails):
        m = r["rfq"]
        print(f"\n=== thread {r['root']} {m['received_at'][11:19]} UTC from {m['from']}: {m['subject']}")
        print("   ", " ".join(m["body"].split())[:700])
        for b in r["bids"]:
            if b["no"] or not b["total"]:
                continue
            took = ""
            print(f"    {b['kind']:7} {b['carrier']:28} {b['total']:>9} {b['currency']} "
                  f"{(b['days'] + ' d') if b['days'] else (str(b['hours']) + ' h')}  {b['ref'] or ''}  {b['at'][11:19]}{took}")
        picks = trucker_picks(r["bids"])
        if picks:
            print("    pickup by rule: " + ", ".join(f"{k} {o.carrier} {o.total}" for k, o in picks.items()))
        for d in r["desk"]:
            print(f"    desk {d['from']}: {d['subject']} | {' '.join(d['body'].split())[:400]}")
        for f in r["follow_ups"]:
            print(f"    follow-up {f['id']} {f['received_at'][11:19]} (re {f.get('in_reply_to')}): "
                  f"{' '.join(f['body'].split())[:300]}")


if __name__ == "__main__":
    if "--offline" not in sys.argv:
        pull()
    show()
