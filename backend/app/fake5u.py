"""A local 5U: mailbox, portal and carriers that answer like the real ones (formats copied from live replies,
Sat 21 Nov). For tests and for trying the whole pipeline without touching the scored system.

Sheet airlines answer with their sheet price; email-only airlines and truckers with fixed prices;
portal prices follow each airline's breaks (deterministic per lane), including the next-break effect.
"""
import itertools
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from . import kit, pricing


class FakeFiveU:
    def __init__(self, mailbox: str = "start-milan@hackloop.mail", reply_now: bool = True):
        self.mailbox = mailbox
        self.ids = itertools.count(1)
        self.inbox: list[dict] = []
        self.outbox: list[dict] = []
        self.all: dict[int, dict] = {}
        self.bookings: dict[str, dict] = {}
        self.rates: dict[str, dict] = {}
        self.reply_now = reply_now
        self.pending: list[dict] = []
        self.lock = threading.Lock()
        self.lanes = {("FRA", "ORD"): [{"code": "BX", "name": "Borealis Freight Airways"}],
                      ("CGN", "DEL"): [{"code": "JP", "name": "Juniper Cargo Lines"},
                                       {"code": "UV", "name": "Ultraviolet Air Freight"}],
                      ("MUC", "JFK"): [{"code": "SL", "name": "Solace Air Cargo"}]}
        self.breaks = {"BX": [0, 45, 100, 300, 500, 1000, 2000], "JP": [0, 45, 100, 300, 500, 1000],
                       "UV": [0, 45, 100, 300, 500, 1000], "SL": [0, 45, 100, 300, 500, 1000, 2000]}

    # ---- what a 5U agent does ------------------------------------------------------------------------------

    def customer(self, sender: str, subject: str, body: str, in_reply_to: int | None = None) -> dict:
        return self._deliver(sender, self.mailbox, subject, body, in_reply_to)

    def _deliver(self, sender: str, to: str, subject: str, body: str, in_reply_to: int | None = None,
                 attachments: list | None = None) -> dict:
        with self.lock:
            mid = next(self.ids)
            parent = self.all.get(in_reply_to) if in_reply_to else None
            refs = (parent["references"] + [parent["id"]]) if parent else []
            m = {"id": mid, "from": sender, "to": to, "subject": subject, "body": body, "in_reply_to": in_reply_to,
                 "references": refs, "received_at": datetime.now(timezone.utc).isoformat(),
                 "attachments": attachments or []}
            self.all[mid] = m
            (self.inbox if to == self.mailbox else self.outbox).append(m)
            return m

    def flush(self) -> None:
        """Deliver the carrier replies that were held back (reply_now=False)."""
        for p in self.pending:
            self._deliver(**p)
        self.pending.clear()

    # ---- API -----------------------------------------------------------------------------------------------

    def poll(self, since_id: int) -> tuple[list[dict], int]:
        with self.lock:
            msgs = [m for m in self.inbox if m["id"] > since_id]
        return msgs, (msgs[-1]["id"] if msgs else since_id)

    def send(self, to: str, subject: str, body: str, in_reply_to: int | None = None) -> dict:
        m = self._deliver(self.mailbox, to, subject, body, in_reply_to)
        reply = self._carrier_reply(m)
        if reply:
            (self._deliver(**reply) if self.reply_now else self.pending.append(reply))
        return m

    def attachment(self, mail_id: int, attachment_id: Any) -> bytes:
        return b""

    def ports(self) -> list[dict]:
        return [{"origin": o, "destination": d, "airlines": a} for (o, d), a in self.lanes.items()]

    def brackets(self, airline: str) -> list[int] | None:
        return self.breaks.get(airline)

    def rate(self, origin: str, destination: str, airline: str, weight_kg: Any, volume_cbm: Any = None) -> dict:
        names = {a["code"]: a["name"] for a in self.lanes.get((origin, destination), [])}
        if airline not in names:
            return {"error": True, "status": 404, "detail": "lane not on portal"}
        cw = pricing.chargeable(Decimal(str(weight_kg)), Decimal(str(volume_cbm)) if volume_cbm else None)
        breaks = self.breaks[airline]
        idx = max(i for i, b in enumerate(breaks) if Decimal(b) <= cw)
        per_kg = Decimal("4.20") - Decimal("0.45") * idx + Decimal(len(airline + destination) % 3) / 10
        rid = f"R-fake{next(self.ids)}"
        r = {"rate_id": rid, "airline": names[airline], "airline_code": airline, "origin": origin,
             "destination": destination, "weight_kg": str(weight_kg), "chargeable_weight_kg": str(cw),
             "total": f"{pricing.money(cw * per_kg):.2f}", "currency": "EUR", "fx_eur_per_usd": None,
             "transit_days": 1 + idx % 3, "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
             "dataset_version": "v1"}
        self.rates[rid] = r
        return r

    def book(self, rate_id: str, team_reference: str) -> tuple[int, dict]:
        if rate_id not in self.rates:
            return 404, {"detail": "unknown rate_id"}
        b = {"booking_reference": f"BK-{len(self.bookings) + 1:04d}", "team_reference": team_reference,
             "rate_id": rate_id, "airline": self.rates[rate_id]["airline"], "price": self.rates[rate_id]["total"],
             "currency": "EUR", "status": "booked"}
        self.bookings[rate_id] = b
        return 201, b

    def board(self) -> dict:
        return {"frozen_at": None, "overview": {"rounds_sent": 0, "teams": 1, "accepted": 0, "bookings": 0},
                "ranking": [], "bookings": [], "rounds": []}

    def board_me(self) -> dict:
        return {"team": "start-milan", "requests": [], "bookings": list(self.bookings.values())}

    # ---- carriers ------------------------------------------------------------------------------------------

    def _carrier_reply(self, m: dict) -> dict | None:
        import re
        c = kit.world().carrier_by_email(m["to"])
        if c is None:
            return None
        base = {"sender": c.email, "to": self.mailbox, "subject": f"Re: {m['subject']}", "in_reply_to": m["id"]}
        if c.kind == "trucker":
            return {**base, "body": f"Hello,\n\nOur total for the pickup is 177.40 EUR. Pickup time: 3 hours.\n\n"
                                    f"Your offer reference is TRK-{m['id']}. No booking is required.\n\n"
                                    f"Best regards,\n{c.name}"}
        if m["subject"].lower().startswith("shipment status"):
            return {**base, "body": "Hello,\n\nyour shipment departed on schedule and is in transit over the "
                                    "Atlantic. Expected arrival: 25 Nov 2026, 14:00 local time.\n\n" + c.name}
        if m["subject"].lower().startswith("booking"):
            return {**base, "body": f"Booking confirmed. Booking reference BK-MAIL-{m['id']}.\n\n{c.name}"}
        lane = re.search(r"Route: ([A-Z]{3}) to ([A-Z]{3})", m["body"])
        kg = re.search(r"(\d+(?:\.\d+)?) kg", m["body"])
        cbm = re.search(r"(\d+(?:\.\d+)?) cbm", m["body"])
        if not (lane and kg):
            return None
        o, d = lane.groups()
        sheet = [l for l in kit.world().sheet(o, d) if l["airline"] == c.name]
        if sheet:
            total, _ = pricing.sheet_price(sheet[0], Decimal(kg.group(1)), Decimal(cbm.group(1)) if cbm else None)
            days = sheet[0]["transit_days"]
        elif d in ("ASU", "KTM", "PPT", "TNR", "ULN"):
            total, days = pricing.money(Decimal(kg.group(1)) * Decimal("5.48")), 5
        else:
            return {**base, "body": f"Hello,\n\nthank you for your request. We do not serve this lane/zone: {o}-{d}.\n\n"
                                    f"Best regards\n{c.name}"}
        return {**base, "body": f"Dear START Milan Forwarding team,\n\nThank you for your inquiry. Our all-in air "
                                f"freight rate from {o} to {d} is {total:.2f} EUR. The transit time is {days} days, "
                                f"and the rate is valid until 21 Nov 2026 23:59 UTC.\n\nPlease quote reference "
                                f"R-mail{m['id']} when booking.\n\nKind regards,\n{c.name}"}
