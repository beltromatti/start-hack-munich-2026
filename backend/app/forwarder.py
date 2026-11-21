"""The forwarder. One loop; all work is derived from the register, so a restart loses nothing and repeats nothing.

    mail in -> stored -> classified by sender (code) -> one task per kind:
      customer  rfq: read (LLM) -> ask carriers by mail + portal + sheets (code) -> wait for bids -> price (code)
                     -> write (LLM) -> reply in the customer's thread. Follow-ups: accept -> book, questions -> reply.
      bid       read (LLM) -> offers attached to the rfq
      tracking  answer from the CRM (code) in human words (LLM)
      tariff    attachment -> text -> lanes (LLM) -> pricing module
Invariant per rfq: exactly one quote, or one question when facts are missing. A quote is never sent twice.
"""
import json
import re
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from . import docs, kit, language, pricing, store
from .config import settings
from .pricing import Offer

TRACKING = "tracking@hackloop.mail"
RATEDESK = "ratedesk@hackloop.mail"


class Forwarder:
    def __init__(self, api: Any):
        self.api = api
        self.pool = ThreadPoolExecutor(max_workers=16)
        self.inflight: set[str] = set()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.fx_eur_per_usd: Decimal | None = None
        self._last_portal = time.time()
        self._last_board = 0.0

    # ---- loop ----------------------------------------------------------------------------------------------

    def start(self) -> threading.Thread:
        kit.load(self.api)
        t = threading.Thread(target=self.run, daemon=True, name="forwarder")
        t.start()
        return t

    def run(self) -> None:
        store.log("router", "info", f"forwarder started, polling every {settings.poll_seconds}s")
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as e:
                store.log("router", "error", f"tick failed: {e!r}")
            self.stop.wait(settings.poll_seconds)

    def tick(self) -> None:
        since = int(store.kv_get("since_id", "0") or 0)
        msgs, nxt = self.api.poll(since)
        for m in msgs:
            if store.save_mail(m, "in"):
                store.log("router", "mail_in", f"{m['from']}: {m.get('subject', '')}"[:200],
                          {"id": m["id"]}, run_id=_run(m))
        if nxt and nxt != since:
            store.kv_set("since_id", str(nxt))
        for m in store.unhandled():
            if float(store.kv_get(f"retry_at:{m['id']}", "0") or 0) > time.time():
                continue
            # one lane per thread: mails of the same thread are handled in order, threads in parallel
            self.submit(f"thread:{m['root']}", self.handle, m)
        for rec in store.records("rfq", "collecting"):
            if self.ready(rec):
                self.submit(f"quote:{rec['id']}", self.send_quote, rec["id"])
        now = time.time()
        if now - self._last_portal > 900:
            self._last_portal = now
            self.submit("portal", kit.refresh_portal, self.api)
        if now - self._last_board > 60:
            self._last_board = now
            self.submit("board", self.watch_board)

    def submit(self, key: str, fn: Callable, *args: Any) -> None:
        with self.lock:
            if key in self.inflight:
                return
            self.inflight.add(key)

        def job() -> None:
            try:
                fn(*args)
            except Exception as e:
                store.log("router", "error", f"{key}: {e!r}", {"trace": traceback.format_exc()[-2000:]})
            finally:
                with self.lock:
                    self.inflight.discard(key)
        self.pool.submit(job)

    # ---- routing (code, by sender) -------------------------------------------------------------------------

    def classify(self, m: dict) -> str:
        """By sender and thread, never by what the mail claims: unknown senders are customers."""
        sender = m["sender"].lower()
        subject = (m["subject"] or "").strip()
        if sender == TRACKING:
            return "tracking"
        if sender == RATEDESK:
            return "ratedesk"
        if re.match(r"^booking\s+\S+\s+confirmed", subject, re.I):
            return "booking"
        if self.rfq_for_bid(m):
            return "bid"
        if kit.world().carrier_by_email(sender):
            if m.get("attachments") or re.search(r"tariff|rate sheet|rates", subject, re.I):
                return "tariff"
            return "other"
        return "customer"

    def handle(self, m: dict) -> None:
        kind = self.classify(m)
        store.log("router", "decision", f"mail {m['id']} -> {kind}", run_id=_run(m))
        try:
            {"customer": self.on_customer, "bid": self.on_bid, "ratedesk": self.on_ratedesk,
             "tracking": self.on_tracking, "tariff": self.on_tariff, "booking": self.on_booking_mail,
             "other": lambda _m: None}[kind](m)
        except Exception:
            tries = int(store.kv_get(f"tries:{m['id']}", "0") or 0) + 1
            store.kv_set(f"tries:{m['id']}", str(tries))
            if tries < 3:  # transient (model or network): try again in 5 s, then 20 s
                store.kv_set(f"retry_at:{m['id']}", str(time.time() + (5 if tries == 1 else 20)))
                raise
        store.mark_handled(m["id"], kind)

    # ---- customer ------------------------------------------------------------------------------------------

    def on_customer(self, m: dict) -> None:
        rid = f"rfq-{m['root']}"
        rec = store.get(rid)
        parsed = language.read_customer(thread_text(m["root"], self.api), run_id=rid)
        store.log("rfq", "info", f"intent {parsed['intent']}", parsed, run_id=rid)
        status = rec["status"] if rec else None
        if status in ("quoted", "booking", "booked", "lost"):
            return self.follow_up(rec, m, parsed)
        if status in ("collecting", "quoting", "held"):
            return  # the quote is on its way (or a person holds it); only the first one counts
        if status == "pricing":  # an earlier attempt stopped half way: quote with what it has, never ask twice
            store.update(rid, lambda r: ("collecting", {**r["data"], "deadline": time.time() + 20}))
            return
        self.start_rfq(rid, m, parsed)

    def start_rfq(self, rid: str, m: dict, p: dict) -> None:
        w = kit.world()
        req = normalise(p, w)
        data = {"root": m["root"], "customer": m["sender"], "subject": m["subject"], "received_at": m["received_at"],
                "last_customer_mail": m["id"], "parsed": p, "request": req, "offers": [], "asked": {}, "replied": [],
                "started": time.time()}
        if req["missing"]:
            store.put(rid, "rfq", "waiting_customer", data)
            body = language.write("question", {"customer_name": p.get("customer_name"), "language": p.get("language"), "their_mail": _body(m),
                                               "missing": req["missing"], "their_request": p.get("notes")}, rid)
            self.reply_customer(rid, m, body)
            return
        store.put(rid, "rfq", "pricing", data)
        o, d, cw = req["origin"], req["destination"], Decimal(req["chargeable_kg"])
        kg, cbm = Decimal(req["weight_kg"]), Decimal(req["volume_cbm"]) if req["volume_cbm"] else None
        offers: list[Offer] = []
        for lane in w.sheet(o, d):  # known prices, instantly
            total, billed = pricing.sheet_price(lane, kg, cbm)
            offers.append(Offer("air", lane["airline"], total, Decimal(lane["transit_days"]), "sheet", None, billed))
        asked: dict[str, str] = {}
        with_sheet = {l["airline"] for l in w.sheet_lanes}
        for c in w.email_airlines(o, d):  # carriers that quote by mail
            weights = [next((x.billed_kg for x in offers if x.carrier == c.name), cw)]
            if c.name not in with_sheet:  # breaks unknown: billing at the next break up may be the cheaper price
                weights += pricing.breaks_to_try(cw)
            for wt in weights:
                asked[str(self.ask_airline(rid, c, o, d, wt, cbm, req))] = c.email
        if req["pickup_zone"]:
            for c in w.truckers(req["pickup_zone"]):
                asked[str(self.ask_trucker(rid, c, req))] = c.email
        portal, failed = self.portal_offers(rid, o, d, kg, cbm, cw)
        offers += portal
        for name in failed:  # portal down or over the limit for this airline: ask the airline by mail instead
            c = w.carrier_by_name(name)
            if c and c.email not in asked.values():
                asked[str(self.ask_airline(rid, c, o, d, cw, cbm, req))] = c.email
        store.update(rid, lambda r: ("collecting", {**r["data"], "asked": asked,
                                                    "offers": r["data"]["offers"] + [x.as_dict() for x in offers],
                                                    "deadline": time.time() + settings.bid_wait_seconds}))
        store.log("rfq", "info", f"{o}-{d} {cw} kg: {len(offers)} prices now, asked {len(asked)} by mail",
                  run_id=rid)

    def ask_airline(self, rid: str, c: kit.Carrier, o: str, d: str, billed: Decimal, cbm: Decimal | None,
                    req: dict) -> int:
        # labelled lines: the carriers' desks read "total weight in kg" (live: "320 kg chargeable" was not read)
        body = (f"Hello {c.name} team,\n\nplease quote air freight for this shipment:\n"
                f"Route: {o} to {d}\nTotal weight: {billed:.0f} kg\n"
                + (f"Volume: {cbm:.2f} cbm\n" if cbm else "")
                + f"Pieces: {req.get('pieces') or 1}\nCargo: general cargo\n"
                f"Ready: {req.get('ready_date') or 'now'}\n\n"
                "Please send your all-in total, currency, transit time, rate reference and validity.\n\n"
                f"Thanks,\n{settings.persona}, {settings.company}")
        sent = self.api.send(c.email, f"Rate request {o}-{d} {billed:.0f} kg", body)
        store.kv_set(f"bidreq:{sent['id']}", rid)
        store.save_mail(sent, "out", "bid_request", handled=True)
        store.log("bids", "mail_out", f"asked {c.name}", {"mail": sent["id"]}, run_id=rid)
        return sent["id"]

    def ask_trucker(self, rid: str, c: kit.Carrier, req: dict) -> int:
        z = kit.world().zones.get(req["pickup_zone"], {})
        body = (f"Hello {c.name} team,\n\nplease quote a pickup from {req.get('pickup_postcode') or ''} "
                f"{z.get('area', '')} (zone {req['pickup_zone']}) to {z.get('airport', req['origin'])} airport.\n"
                f"Total weight: {Decimal(req['weight_kg']):.0f} kg\n"
                + (f"Volume: {Decimal(req['volume_cbm']):.2f} cbm\n" if req.get("volume_cbm") else "")
                + f"Pieces: {req.get('pieces') or 1}\nPickup: {req.get('ready_date') or 'as soon as possible'}\n\n"
                f"Please send your total, currency, pickup time and offer reference.\n\nThanks,\n"
                f"{settings.persona}, {settings.company}")
        sent = self.api.send(c.email, f"Pickup quote zone {req['pickup_zone']} to {z.get('airport', '')}", body)
        store.kv_set(f"bidreq:{sent['id']}", rid)
        store.save_mail(sent, "out", "bid_request", handled=True)
        store.log("bids", "mail_out", f"asked {c.name}", {"mail": sent["id"]}, run_id=rid)
        return sent["id"]

    def portal_offers(self, rid: str, o: str, d: str, kg: Decimal, cbm: Decimal | None,
                      cw: Decimal) -> tuple[list[Offer], set[str]]:
        """Portal prices at the chargeable weight and at the next break; airlines the portal failed for."""
        w, out, failed = kit.world(), [], set()
        for a in w.portal.get((o, d), []):
            weights = [kg]
            nb = pricing.next_break(w.brackets.get(a["code"], []), cw)
            if nb is not None and nb / cw < Decimal("1.5"):
                weights.append(nb)  # billing at the next break is often cheaper (rates fall < 1.5x per break)
            for wt in weights:
                r = self.api.rate(o, d, a["code"], wt, cbm)
                if r.get("error"):
                    store.log("rfq", "error", f"portal {a['code']} {o}-{d}: {r['status']} {r['detail']}"[:300],
                              run_id=rid)
                    if r["status"] in (429, 500, 502, 503, 504) and wt == kg:
                        failed.add(a["name"])
                    continue
                total = self.eur(Decimal(r["total"]), r["currency"], r.get("fx_eur_per_usd"))
                if total is None:
                    continue
                out.append(Offer("air", r["airline"], total, Decimal(r["transit_days"]), "portal", r["rate_id"],
                                 Decimal(r["chargeable_weight_kg"]),
                                 extra={"code": a["code"], "valid_until": r["valid_until"], "weight": str(wt)}))
        return out, failed

    def ready(self, rec: dict) -> bool:
        d = rec["data"]
        if time.time() >= d.get("deadline", 0):
            return True
        # every request mail answered: a carrier asked at two weights answers twice
        asked, replied = Counter(d["asked"].values()), Counter(d["replied"])
        return all(replied[email] >= n for email, n in asked.items())

    def send_quote(self, rid: str) -> None:
        claimed = store.update(rid, lambda r: ("quoting", r["data"]) if r["status"] == "collecting" else None)
        if not claimed or claimed["status"] != "quoting":
            return
        d = claimed["data"]
        req = d["request"]
        offers = [Offer.of(x) for x in d["offers"]]
        q = pricing.quote([x for x in offers if x.leg == "air"], [x for x in offers if x.leg == "pickup"],
                          req["preference"], bool(req["pickup_zone"]))
        m = store.mail(d["last_customer_mail"])
        p = d["parsed"]
        if q is None:
            if time.time() - d["started"] < 3 * settings.bid_wait_seconds:  # nothing yet: give carriers more time
                store.update(rid, lambda r: ("collecting", {**r["data"], "deadline": time.time() + 15}))
                return
            body = language.write("decline", {"customer_name": p.get("customer_name"), "language": p.get("language"), "their_mail": _body(m),
                                              "reason": f"no carrier offers {req['origin']} to {req['destination']}"},
                                  rid)
            self.reply_customer(rid, m, body)
            store.update(rid, lambda r: ("lost", {**r["data"], "reason": "no offer"}))
            return
        amount = pricing.fmt(Decimal(q["total"]), q["currency"])
        facts = {"customer_name": p.get("customer_name"), "language": p.get("language"), "their_mail": _body(m),
                 "route": f"{req['origin']} to {req['destination']}", "airline": q["air"]["carrier"],
                 "transit_days": q["transit_days"], "preference": req["preference"],
                 "cargo": f"{req.get('pieces') or ''} pcs {Decimal(req['weight_kg']):.0f} kg".strip(),
                 "pickup": f"truck pickup from {req.get('pickup_postcode') or req['pickup_zone']} by "
                           f"{q['pickup']['carrier']}" if q["pickup"] else None,
                 "commodity": p.get("commodity")}
        body = language.write("quote", facts, rid, amount)
        sent = self.reply_customer(rid, m, body)
        took = time.time() - _ts(d["received_at"])
        store.update(rid, lambda r: ("quoted", {**r["data"], "quote": q, "amount": amount, "quote_mail": sent["id"],
                                                "quoted_at": time.time(), "response_seconds": round(took, 1)}))
        store.log("rfq", "decision", f"quoted {amount} ({q['air']['carrier']}, {q['transit_days']} d) in {took:.0f}s",
                  q, run_id=rid)

    def reply_customer(self, rid: str, m: dict, body: str) -> dict:
        subject = m["subject"] if (m["subject"] or "").lower().startswith("re:") else f"Re: {m['subject']}"
        sent = self.api.send(m["sender"], subject, body, in_reply_to=m["id"])
        store.save_mail(sent, "out", "reply", handled=True)
        store.log("rfq", "mail_out", f"to {m['sender']}: {body[:120]}", {"mail": sent["id"], "body": body},
                  run_id=rid)
        return sent

    def follow_up(self, rec: dict, m: dict, p: dict) -> None:
        rid, d = rec["id"], rec["data"]
        store.update(rid, lambda r: (r["status"], {**r["data"], "last_customer_mail": m["id"]}))
        if p["intent"] == "accept" and rec["status"] == "quoted" and d.get("quote"):
            return self.book(rid, m)
        if p["intent"] == "decline":
            store.update(rid, lambda r: ("lost", {**r["data"], "reason": p.get("notes") or "declined"}))
            return
        facts = {"customer_name": p.get("customer_name"), "language": p.get("language"), "their_mail": _body(m),
                 "their_message": p.get("notes"), "status": rec["status"], "our_quote": d.get("amount"),
                 "airline": (d.get("quote") or {}).get("air", {}).get("carrier"),
                 "transit_days": (d.get("quote") or {}).get("transit_days"),
                 "booking": d.get("booking")}
        self.reply_customer(rid, m, language.write("reply", facts, rid, d.get("amount")))

    # ---- booking -------------------------------------------------------------------------------------------

    def book(self, rid: str, m: dict) -> None:
        rec = store.update(rid, lambda r: ("booking", r["data"]) if r["status"] == "quoted" else None)
        if not rec or rec["status"] != "booking":
            return
        d = rec["data"]
        air = d["quote"]["air"]
        ref = f"SM-{d['root']}"
        status, body = (0, {})
        if air.get("rate_id"):
            status, body = self.api.book(air["rate_id"], ref)
            if status == 410 and air.get("extra", {}).get("code"):  # expired: fresh rate, same airline and weight
                req = d["request"]
                r = self.api.rate(req["origin"], req["destination"], air["extra"]["code"],
                                  air["extra"].get("weight") or req["weight_kg"], req.get("volume_cbm"))
                if not r.get("error"):
                    status, body = self.api.book(r["rate_id"], ref)
        store.log("booking", "info", f"portal booking {air.get('rate_id')}: {status}", body, run_id=rid)
        booking = {"team_reference": ref, "rfq": rid, "customer": d["customer"], "airline": air["carrier"],
                   "route": f"{d['request']['origin']}-{d['request']['destination']}",
                   "transit_days": d["quote"]["transit_days"], "amount": d["amount"], "booked_at": time.time(),
                   "ready_date": d["request"].get("ready_date"), "pickup": d["quote"].get("pickup"),
                   "weight_kg": d["request"]["weight_kg"], "pieces": d["request"].get("pieces"),
                   "rate_id": air.get("rate_id")}
        if status in (200, 201):
            booking.update(booking_reference=body.get("booking_reference"), status="booked", via="portal")
        elif air.get("email"):  # book by mail with the airline, in its bid thread
            text = (f"Hello,\n\nwe would like to book your offer {air.get('rate_id') or ''} "
                    f"({booking['route']}, {Decimal(d['request']['weight_kg']):.0f} kg). Our reference: {ref}.\n\n"
                    f"Thanks,\n{settings.persona}, {settings.company}")
            sent = self.api.send(air["email"], f"Booking {air.get('rate_id') or ref}", text,
                                 in_reply_to=air.get("reply_mail"))
            store.save_mail(sent, "out", "booking_request", handled=True)
            store.kv_set(f"bidreq:{sent['id']}", rid)
            booking.update(status="requested", via="email")
        else:
            booking.update(status="failed", via="portal", error=body)
        store.put(f"booking-{d['root']}", "booking", booking["status"], booking)
        store.update(rid, lambda r: ("booked" if booking["status"] != "failed" else "quoted",
                                     {**r["data"], "booking": booking}))
        p = d["parsed"]
        facts = {"customer_name": p.get("customer_name"), "language": p.get("language"), "their_mail": _body(m),
                 "booking_reference": booking.get("booking_reference") or ref, "our_reference": ref,
                 "airline": booking["airline"], "route": booking["route"], "transit_days": booking["transit_days"],
                 "pickup_by": (booking.get("pickup") or {}).get("carrier")}
        if booking["status"] != "failed":
            self.reply_customer(rid, m, language.write("booked", facts, rid))

    def on_booking_mail(self, m: dict) -> None:
        text = f"{m['subject']}\n{m['body']}"
        for rec in store.records("booking"):
            b = rec["data"]
            if any(x and x in text for x in (b.get("rate_id"), b.get("team_reference"), b.get("booking_reference"))):
                ref = re.search(r"Booking\s+(\S+)\s+confirmed", m["subject"] or "", re.I)
                b = {**b, "status": "confirmed", "confirmation_mail": m["id"],
                     "booking_reference": b.get("booking_reference") or (ref.group(1) if ref else None)}
                store.put(rec["id"], "booking", "confirmed", b)
                store.log("booking", "info", f"confirmed {b.get('booking_reference')}", run_id=b["rfq"])
                return
        store.log("booking", "info", f"confirmation not matched: {m['subject']}")

    # ---- bids ----------------------------------------------------------------------------------------------

    def rfq_for_bid(self, m: dict) -> str | None:
        for k in (m.get("in_reply_to"), m.get("root")):
            if k is not None:
                rid = store.kv_get(f"bidreq:{k}")
                if rid:
                    return rid
        return None

    def on_bid(self, m: dict) -> None:
        rid = self.rfq_for_bid(m)
        if rid is None:
            return
        rec = store.get(rid)
        if rec and rec["status"] in ("booking", "booked") and re.search(r"confirm|booked", m["body"], re.I):
            return self.on_booking_mail(m)
        carrier = kit.world().carrier_by_email(m["sender"])
        offers = [self.offer(o, m, carrier) for o in language.read_bid(m["sender"], m["subject"], m["body"], rid)]
        offers = [o for o in offers if o is not None]
        store.update(rid, lambda r: (r["status"], {**r["data"], "replied": r["data"]["replied"] + [m["sender"]],
                                                   "offers": r["data"]["offers"] + [o.as_dict() for o in offers]}))
        store.log("bids", "info", f"{m['sender']}: " + ", ".join(f"{o.carrier} {o.total}" for o in offers) or "no offer",
                  run_id=rid)

    def offer(self, o: dict, m: dict, carrier: kit.Carrier | None) -> Offer | None:
        if not o.get("available") or o.get("total") is None:
            return None
        total = self.eur(Decimal(str(o["total"])), o.get("currency") or "EUR", None)
        if total is None:
            return None
        trucker = carrier is not None and carrier.kind == "trucker"
        days = (Decimal(str(o["pickup_hours"])) / 24).quantize(Decimal("0.001")) if trucker and o.get("pickup_hours") is not None else \
            Decimal(str(o.get("transit_days") or 0))
        # a carrier answering for itself is named as in the carrier list (so its mail bid and its sheet price
        # are recognised as the same carrier); the rate desk names the airlines it lists
        name = carrier.name if carrier else (o.get("carrier") or m["sender"])
        return Offer("pickup" if trucker else "air", name, total, days, "email", o.get("reference"),
                     reply_mail=m["id"], email=m["sender"], extra={"valid_until": o.get("valid_until"),
                                                                   "note": o.get("note")})

    def on_ratedesk(self, m: dict) -> None:
        lane = re.search(r"\b([A-Z]{3})-([A-Z]{3})\b", m["subject"] or "")
        if not lane:
            return
        for rec in store.records("rfq", "collecting"):
            req = rec["data"]["request"]
            if (req["origin"], req["destination"]) == lane.groups():
                offers = [self.offer(o, m, None) for o in language.read_bid(m["sender"], m["subject"], m["body"],
                                                                             rec["id"])]
                offers = [o for o in offers if o is not None]
                for o in offers:
                    o.source = "ratedesk"
                store.update(rec["id"], lambda r: (r["status"], {
                    **r["data"], "replied": r["data"]["replied"] + [RATEDESK],
                    "offers": r["data"]["offers"] + [o.as_dict() for o in offers]}))

    def eur(self, amount: Decimal, currency: str, fx: Any) -> Decimal | None:
        cur = (currency or "EUR").upper()
        if fx:
            self.fx_eur_per_usd = Decimal(str(fx))
        if cur == "EUR":
            return pricing.money(amount)
        if cur == "USD" and self.fx_eur_per_usd:
            return pricing.money(amount * self.fx_eur_per_usd)
        store.log("bids", "error", f"cannot convert {amount} {cur} to EUR")
        return None

    # ---- tracking ------------------------------------------------------------------------------------------

    def on_tracking(self, m: dict) -> None:
        text = f"{m['subject']}\n{m['body']}"
        match = None
        for rec in store.records("booking"):
            b = rec["data"]
            if any(x and str(x) in text for x in (b.get("booking_reference"), b.get("team_reference"),
                                                   b.get("rate_id"))):
                match = b
                break
        facts: dict[str, Any] = {"question": m["body"][:1500]}
        if match:
            booked = datetime.fromtimestamp(match["booked_at"], timezone.utc)
            facts.update({k: match.get(k) for k in ("booking_reference", "team_reference", "airline", "route",
                                                    "transit_days", "weight_kg", "pieces", "status")})
            facts["booked_on"] = booked.strftime("%d %b %Y %H:%M UTC")
            facts["estimated_arrival"] = (booked + timedelta(days=float(match["transit_days"]))).strftime("%d %b %Y")
            facts["pickup_by"] = (match.get("pickup") or {}).get("carrier")
        else:
            facts["note"] = "no booking with that reference in our system; ask for the booking reference"
        run = match["rfq"] if match else f"tracking-{m['id']}"
        body = language.write("tracking", facts, run)
        subj = m["subject"] or "Your shipment"
        sent = self.api.send(m["sender"], subj if subj.lower().startswith("re:") else f"Re: {subj}", body,
                             in_reply_to=m["id"])
        store.save_mail(sent, "out", "tracking_answer", handled=True)
        store.log("tracking", "mail_out", f"answered {m['id']}", {"body": body, "facts": facts}, run_id=run)

    # ---- tariffs -------------------------------------------------------------------------------------------

    def on_tariff(self, m: dict) -> None:
        carrier = kit.world().carrier_by_email(m["sender"])
        parts, images = [m["body"]], []
        for a in m.get("attachments") or []:
            name = (a.get("filename") or "").lower()
            try:
                raw = self.api.attachment(m["id"], a.get("id"))
                if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):  # a scanned sheet: the model looks at it
                    images.append(("image/png" if name.endswith(".png") else "image/jpeg", raw))
                else:
                    parts.append(f"[{a.get('filename')}]\n" + docs.text(name, raw))
            except Exception as e:
                store.log("tariff", "error", f"attachment {a.get('filename')}: {e!r}")
        out = language.read_tariff("\n\n".join(parts)[:60000], run_id=f"tariff-{m['id']}", images=images or None)
        airline = carrier.name if carrier else (out.get("airline") or m["sender"])
        lanes = []
        for l in out["lanes"]:
            rates = [_num(x) for x in l["rates_per_kg"]]
            fixed = [_num(l["minimum"]), _num(l["fuel_per_kg"]), _num(l["security_per_kg"])]
            if not l["breaks_kg"] or len(l["breaks_kg"]) != len(rates) or None in rates + fixed:
                continue
            lanes.append({"airline": airline, "origin": l["origin"].upper(), "destination": l["destination"].upper(),
                          "transit_days": l["transit_days"] or 0, "minimum_eur": fixed[0],
                          "breaks_kg": [int(b) for b in l["breaks_kg"]], "rates_eur_per_kg": rates,
                          "fuel_eur_per_kg": fixed[1], "security_eur_per_kg": fixed[2]})
        if lanes and (out.get("currency") or "EUR").upper() == "EUR":
            kit.replace_sheet(airline, lanes, f"mail {m['id']}")
        store.log("tariff", "info", f"{airline}: {len(lanes)} lanes ingested", {"notes": out.get("notes")},
                  run_id=f"tariff-{m['id']}")

    # ---- watcher -------------------------------------------------------------------------------------------

    def watch_board(self) -> None:
        board = self.api.board_me()
        store.kv_set("board_me", json.dumps(board))
        seen = set((store.kv_get("board_seen") or "").split(","))
        for r in board.get("requests", []):
            key = f"{r.get('round')}:{r.get('verdict')}"
            if key not in seen and r.get("verdict") not in ("open", "pending"):
                seen.add(key)
                store.log("watcher", "info", f"round {r.get('round')}: {r.get('verdict')} {r.get('reason') or ''}"
                          f" points {r.get('points')}"[:300], r)
        store.kv_set("board_seen", ",".join(sorted(x for x in seen if x)))


# ---- helpers -----------------------------------------------------------------------------------------------

def normalise(p: dict, w: kit.World) -> dict:
    """From what the customer wrote (as read by the model) to the facts code prices with."""
    pieces = p.get("pieces")
    kg = language.weight_kg(p.get("weight") or {}, pieces)
    cbm = language.volume_cbm(p.get("volume") or {}, p.get("dimensions") or [], pieces)
    zone = None
    postcode = re.sub(r"\D", "", p.get("pickup_postcode") or "")
    if p.get("pickup_needed") and len(postcode) >= 2:
        zone = postcode[:2] if postcode[:2] in w.zones else None
    if p.get("pickup_needed") and not zone and p.get("pickup_city"):  # "pickup in Darmstadt": the zone's area
        city = p["pickup_city"].strip().lower()
        zone = next((z for z, v in w.zones.items() if v["area"].lower() == city), None) or \
            next((z for z, v in w.zones.items() if city in v["area"].lower() or v["area"].lower() in city), None)
    origin = (p.get("origin_airport") or "").upper() or None
    if zone and not origin:
        origin = w.zones[zone]["airport"]
    if zone and origin and w.zones[zone]["airport"] != origin:
        origin = w.zones[zone]["airport"]  # the truck goes to the zone's airport
    dest = (p.get("destination_airport") or "").upper() or None
    missing = []
    if not origin or origin not in w.origins():
        missing.append("the pickup address or departure airport in Germany")
    if p.get("pickup_needed") and not zone:
        missing.append("the pickup postcode")
    if not dest:
        missing.append("the destination airport or city")
    if kg is None:
        missing.append("the total weight")
    cw = pricing.chargeable(kg, cbm) if kg else None
    return {"origin": origin, "destination": dest, "weight_kg": str(kg) if kg else None,
            "volume_cbm": str(cbm.quantize(Decimal("0.001"))) if cbm else None,
            "chargeable_kg": str(cw) if cw else None, "pieces": pieces, "pickup_zone": zone,
            "pickup_postcode": p.get("pickup_postcode"), "preference": p.get("preference") or "unspecified",
            "ready_date": p.get("ready_date"), "commodity": p.get("commodity"), "flags": p.get("flags") or [],
            "missing": sorted(set(missing))}


def thread_text(root: int, api: Any = None) -> str:
    """The whole thread as the model reads it, attachments included (a packing list, a spec sheet)."""
    out = []
    for x in store.thread(root):
        who = "US (the forwarder)" if x["direction"] == "out" else x["sender"]
        text = f"--- mail {x['id']} from {who} at {x['received_at'] or ''}\nSubject: {x['subject']}\n\n{x['body']}"
        for a in (x.get("attachments") or []) if api is not None and x["direction"] == "in" else []:
            try:
                text += f"\n\n[attachment {a.get('filename')}]\n" + docs.text(a.get("filename", ""), api.attachment(
                    x["id"], a.get("id")))[:6000]
            except Exception as e:
                store.log("rfq", "error", f"attachment {a.get('filename')}: {e!r}")
        out.append(text)
    return "\n\n".join(out)[-16000:]


def _num(x: Any) -> str | None:
    """'EUR 1,234.50' / '3,71' -> '1234.50' / '3.71' (amounts from a sheet, read by the model)."""
    t = re.sub(r"[^\d.,]", "", str(x or ""))
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return str(Decimal(t))
    except Exception:
        return None


def _body(m: dict | None) -> str:
    return ((m or {}).get("body") or "")[:1500]


def _run(m: dict) -> str:
    if m.get("root"):
        return f"rfq-{m['root']}"
    refs = m.get("references") or []
    return f"rfq-{refs[0] if refs else m['id']}"


def _ts(iso: str | None) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else time.time()
    except ValueError:
        return time.time()
