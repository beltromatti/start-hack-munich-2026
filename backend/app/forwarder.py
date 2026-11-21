"""The system under the forwarder agent: it guarantees, the agent decides.

    mail in -> register -> routed by sender and thread (code)
      customer / tracking   -> the forwarder agent, one session per thread (agent.py), with tools (tools.py)
      carrier / rate desk   -> read into offers on the deal (small model), wakes nobody (no cascades)
      tariff                -> pricing module          booking confirmation -> CRM

Work is derived from the register: a restart loses nothing and repeats nothing. One lane per thread.
The engine below is what the tools run: carriers asked, portal priced, sheets computed, options built, bookings.
"""
import json
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any, Callable

from . import agent, anomaly, docs, kit, language, pricing, store
from .config import settings
from .pricing import Offer

from .kit import RATEDESK, TRACKING


class Forwarder:
    def __init__(self, api: Any):
        self.api = api
        self.pool = ThreadPoolExecutor(max_workers=24)
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
                store.log("router", "mail_in", f"{m['from']}: {m.get('subject', '')}"[:200], {"id": m["id"]},
                          run_id=f"deal-{_root(m)}")
        if nxt and nxt != since:
            store.kv_set("since_id", str(nxt))
        for m in store.unhandled():
            if float(store.kv_get(f"retry_at:{m['id']}", "0") or 0) > time.time():
                continue
            self.submit(f"thread:{m['root']}", self.handle, m)  # one lane per thread, threads in parallel
        for box in store.records("inbox", "pending"):  # a person, or news from the world, for a session
            self.submit(f"thread:{box['data']['root']}", agent.resume_inbox, self, box["id"])
        now = time.time()
        if now - self._last_portal > 900:
            self._last_portal = now
            self.submit("portal", kit.refresh_portal, self.api)
        if now - self._last_board > 30:
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

    # ---- routing (code, by sender and thread) --------------------------------------------------------------

    def classify(self, m: dict) -> str:
        """By sender and thread, never by what a mail claims about itself. Unknown senders are customers."""
        sender = m["sender"].lower()
        subject = (m["subject"] or "").strip()
        if sender == TRACKING:
            return "tracking"
        if sender == RATEDESK:
            return "ratedesk"
        if re.match(r"^booking\s+\S+\s+confirmed", subject, re.I):
            return "booking"
        if self.deal_for_bid(m):
            return "bid"
        if kit.world().carrier_by_email(sender):
            if m.get("attachments") or re.search(r"tariff|rate sheet|rates", subject, re.I):
                return "tariff"
            return "other"
        return "customer"

    def handle(self, m: dict) -> None:
        kind = self.classify(m)
        store.log("router", "decision", f"mail {m['id']} -> {kind}", run_id=f"deal-{m['root']}")
        try:
            if kind in ("customer", "tracking"):
                agent.on_mail(self, m, kind)
            else:
                {"bid": self.on_bid, "ratedesk": self.on_ratedesk, "tariff": self.on_tariff,
                 "booking": self.on_booking_mail, "other": lambda _m: None}[kind](m)
        except Exception:
            tries = int(store.kv_get(f"tries:{m['id']}", "0") or 0) + 1
            store.kv_set(f"tries:{m['id']}", str(tries))
            if tries < 3:  # transient: try again in 5 s, then 20 s
                store.kv_set(f"retry_at:{m['id']}", str(time.time() + (5 if tries == 1 else 20)))
                raise
        store.mark_handled(m["id"], kind)

    # ---- engine: offers ------------------------------------------------------------------------------------

    def collect_offers(self, deal_id: str, shipment: dict | None, preference: str, wait: float) -> dict:
        """Ask everyone who can carry it (mail, portal, sheets), wait for the answers, return priced options."""
        w = kit.world()
        deal = store.get(deal_id)
        if shipment is not None:
            req = normalise(shipment, w)
            if req["missing"]:
                return {"missing": req["missing"], "understood": req,
                        "destinations_we_fly_to": sorted({d for c in w.carriers if c.kind == "airline"
                                                          for d in c.serves} | {d for _, d in w.portal}),
                        "hint": "if the customer's words already say it (a city is its airport), call again with it; "
                                "otherwise ask the customer for exactly this"}
            same = deal and deal["data"].get("request") and all(
                deal["data"]["request"].get(k) == req.get(k)
                for k in ("origin", "destination", "chargeable_kg", "pickup_zone", "volume_cbm"))
            if not same:
                self._ask_everyone(deal_id, req)
        deal = store.get(deal_id)
        if not deal or not deal["data"].get("request"):
            return {"error": "no shipment yet: call get_offers with the shipment"}
        end = time.time() + max(0.0, float(wait))
        while time.time() < end:
            d = store.get(deal_id)["data"]
            if set(d.get("asked", {}).values()) <= set(d.get("replied", [])):
                break
            self.wait_step()
        return self.options(deal_id, preference)

    def wait_step(self) -> None:
        """While a tool waits for carriers, the loop's other threads read their replies."""
        time.sleep(0.5)

    def _ask_everyone(self, deal_id: str, req: dict) -> None:
        w = kit.world()
        o, d, cw = req["origin"], req["destination"], Decimal(req["chargeable_kg"])
        kg, cbm = Decimal(req["weight_kg"]), Decimal(req["volume_cbm"]) if req["volume_cbm"] else None
        offers: list[Offer] = []
        for lane in w.sheet(o, d):  # known prices, instantly
            total, billed = pricing.sheet_price(lane, kg, cbm)
            offers.append(Offer("air", lane["airline"], total, Decimal(lane["transit_days"]), "sheet", None, billed))
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "request": req, "offers": [x.as_dict() for x in offers],
                                                       "asked": {}, "replied": [], "asked_at": time.time()}))
        asked: dict[str, str] = {}
        for c in w.email_airlines(o, d):  # carriers that quote by mail
            billed = next((x.billed_kg for x in offers if x.carrier == c.name), cw)
            asked[str(self.ask_airline(deal_id, c, o, d, billed, cbm, req))] = c.email
        if req["pickup_zone"]:
            for c in w.truckers(req["pickup_zone"]):
                asked[str(self.ask_trucker(deal_id, c, req))] = c.email
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "asked": {**r["data"]["asked"], **asked}}))
        portal, failed = self.portal_offers(deal_id, o, d, kg, cbm, cw)
        for name in failed:  # portal down or over the limit for this airline: ask the airline by mail
            c = w.carrier_by_name(name)
            if c and c.email not in asked.values():
                asked[str(self.ask_airline(deal_id, c, o, d, cw, cbm, req))] = c.email
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "asked": {**r["data"]["asked"], **asked},
                                                       "offers": r["data"]["offers"] + [x.as_dict() for x in portal]}))
        store.log("bids", "info", f"{o}-{d} {cw} kg: {len(offers) + len(portal)} prices now, asked {len(asked)} by mail",
                  run_id=deal_id)

    def options(self, deal_id: str, preference: str) -> dict:
        """The priced options as the agent sees them. Every number here is computed by code."""
        d = store.get(deal_id)["data"]
        req = d["request"]
        offers = [Offer.of(x) for x in d.get("offers", [])]
        air = sorted(pricing.best_by_carrier([x for x in offers if x.leg == "air"]), key=lambda o: o.total)
        pickups = sorted(pricing.best_by_carrier([x for x in offers if x.leg == "pickup"]), key=lambda o: o.total)
        needs_pickup = bool(req["pickup_zone"])
        table: dict[str, dict] = {}
        rows = []
        for i, a in enumerate(air, 1):
            p_cheap = pricing.pick(pickups, "cheapest") if needs_pickup else None
            p_fast = pricing.pick(pickups, "fastest") if needs_pickup else None
            for tag, p in ([("", p_cheap)] if not needs_pickup or p_cheap is p_fast else
                           [("", p_cheap), ("f", p_fast)]):
                if needs_pickup and p is None:
                    continue
                oid = f"A{i}{tag}"
                total = pricing.money(a.total + (p.total if p else 0))
                table[oid] = {"air": a.as_dict(), "pickup": p.as_dict() if p else None, "total": str(total),
                              "total_text": pricing.fmt(total)}
                rows.append({"option": oid, "airline": a.carrier, "transit_days": float(a.days),
                             "pickup": {"trucker": p.carrier, "pickup_hours": round(float(p.days) * 24, 1)} if p else None,
                             "total": pricing.fmt(total), "source": a.source, "bookable_reference": a.rate_id,
                             "carrier_note": (a.extra or {}).get("note")})
        rec = {}
        for pref in ("cheapest", "fastest", "balanced"):
            cand = [Offer("air", k, Decimal(v["total"]),
                          Decimal(v["air"]["days"]) + (Decimal(v["pickup"]["days"]) if v["pickup"] else 0), "x")
                    for k, v in table.items()]
            best = pricing.pick(cand, pref if pref != "balanced" else "unspecified")
            if best:
                rec[pref] = best.carrier
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "options": table}))
        waiting = sorted(set(d.get("asked", {}).values()) - set(d.get("replied", [])))
        pref_key = preference if preference in ("cheapest", "fastest") else "balanced"
        return {"shipment": {k: req[k] for k in ("origin", "destination", "weight_kg", "volume_cbm", "chargeable_kg",
                                                 "pieces", "pickup_zone", "pickup_postcode")},
                "options": rows, "recommended": rec.get(pref_key), "recommended_for": pref_key,
                "recommended_by_preference": rec,
                "pickup_alternatives": [{"trucker": p.carrier, "total": pricing.fmt(p.total),
                                         "pickup_hours": round(float(p.days) * 24, 1)} for p in pickups],
                "still_waiting_for": waiting}

    def ask_airline(self, deal_id: str, c: kit.Carrier, o: str, d: str, billed: Decimal, cbm: Decimal | None,
                    req: dict) -> int:
        # labelled lines: the carriers' desks read "Total weight: N kg" (live: "320 kg chargeable" was not read)
        body = (f"Hello {c.name} team,\n\nplease quote air freight for this shipment:\n"
                f"Route: {o} to {d}\nTotal weight: {billed:.0f} kg\n"
                + (f"Volume: {cbm:.2f} cbm\n" if cbm else "")
                + f"Pieces: {req.get('pieces') or 1}\nCargo: general cargo\n"
                f"Ready: {req.get('ready_date') or 'now'}\n\n"
                "Please send your all-in total, currency, transit time, rate reference and validity.\n\n"
                f"Thanks,\n{settings.persona}, {settings.company}")
        return self.mail_carrier(deal_id, c.email, f"Rate request {o}-{d} {billed:.0f} kg", body)

    def ask_trucker(self, deal_id: str, c: kit.Carrier, req: dict) -> int:
        z = kit.world().zones.get(req["pickup_zone"], {})
        body = (f"Hello {c.name} team,\n\nplease quote a pickup from {req.get('pickup_postcode') or ''} "
                f"{z.get('area', '')} (zone {req['pickup_zone']}) to {z.get('airport', req['origin'])} airport.\n"
                f"Total weight: {Decimal(req['weight_kg']):.0f} kg\n"
                + (f"Volume: {Decimal(req['volume_cbm']):.2f} cbm\n" if req.get("volume_cbm") else "")
                + f"Pieces: {req.get('pieces') or 1}\nPickup: {req.get('ready_date') or 'as soon as possible'}\n\n"
                f"Please send your total, currency, pickup time and offer reference.\n\nThanks,\n"
                f"{settings.persona}, {settings.company}")
        return self.mail_carrier(deal_id, c.email, f"Pickup quote zone {req['pickup_zone']} to {z.get('airport', '')}",
                                 body)

    def mail_carrier(self, deal_id: str, to: str, subject: str, body: str, in_reply_to: int | None = None) -> int:
        """Every mail to a carrier belongs to a deal: its answer comes back to that deal's offers."""
        sent = self.api.send(to, subject, body, in_reply_to=in_reply_to)
        store.kv_set(f"bidreq:{sent['id']}", deal_id)
        store.save_mail(sent, "out", "to_carrier", handled=True)
        store.log("bids", "mail_out", f"to {to}: {subject}", {"mail": sent["id"], "body": body}, run_id=deal_id)
        return sent["id"]

    def portal_offers(self, deal_id: str, o: str, d: str, kg: Decimal, cbm: Decimal | None,
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
                    store.log("bids", "error", f"portal {a['code']} {o}-{d}: {r['status']} {r['detail']}"[:300],
                              run_id=deal_id)
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

    # ---- engine: booking -----------------------------------------------------------------------------------

    def book_option(self, deal_id: str, option_id: str) -> dict:
        deal = store.get(deal_id)
        d = deal["data"]
        opt = (d.get("options") or {}).get(option_id)
        if not opt:
            return {"error": f"unknown option {option_id}", "options": list((d.get("options") or {}).keys())}
        air, req = opt["air"], d["request"]
        ref = f"SM-{d['root']}"
        status, body = 0, {}
        if air.get("rate_id"):
            status, body = self.api.book(air["rate_id"], ref)
            if status == 410 and (air.get("extra") or {}).get("code"):  # expired: fresh rate, same airline and weight
                r = self.api.rate(req["origin"], req["destination"], air["extra"]["code"],
                                  air["extra"].get("weight") or req["weight_kg"], req.get("volume_cbm"))
                if not r.get("error"):
                    status, body = self.api.book(r["rate_id"], ref)
                    body = {**body, "note": f"the quoted rate had expired; booked a fresh rate at {r['total']} "
                                            f"{r['currency']}"}
        store.log("booking", "info", f"portal booking {air.get('rate_id')}: {status}", body, run_id=deal_id)
        booking = {"team_reference": ref, "deal": deal_id, "customer": d["customer"], "airline": air["carrier"],
                   "route": f"{req['origin']}-{req['destination']}", "transit_days": air["days"],
                   "amount": opt["total_text"], "option": option_id, "booked_at": time.time(),
                   "ready_date": req.get("ready_date"), "pickup": opt.get("pickup"), "weight_kg": req["weight_kg"],
                   "pieces": req.get("pieces"), "rate_id": air.get("rate_id")}
        if status in (200, 201):
            booking.update(booking_reference=body.get("booking_reference"), status="booked", via="portal",
                           price=body.get("price"), currency=body.get("currency"), note=body.get("note"))
        elif air.get("email") or kit.world().carrier_by_name(air["carrier"]):  # by mail with the airline
            air = {**air, "email": air.get("email") or kit.world().carrier_by_name(air["carrier"]).email}
            text = (f"Hello,\n\nwe would like to book your offer {air.get('rate_id') or ''} ({booking['route']}, "
                    f"{Decimal(air.get('billed_kg') or req['weight_kg']):.0f} kg). Our reference: {ref}.\n\n"
                    f"Thanks,\n{settings.persona}, {settings.company}")
            self.mail_carrier(deal_id, air["email"], f"Booking {air.get('rate_id') or ref}", text,
                              in_reply_to=air.get("reply_mail"))
            booking.update(status="requested", via="email", portal_answer={"status": status, "body": body})
        else:
            booking.update(status="failed", via="portal", error={"status": status, "body": body})
        store.put(f"booking-{d['root']}", "booking", booking["status"], booking)
        if booking["status"] != "failed":
            store.update(deal_id, lambda r: ("booked", {**r["data"], "booking": booking}))
        return booking

    # ---- carrier mail (system tasks, no agent) -------------------------------------------------------------

    def deal_for_bid(self, m: dict) -> str | None:
        for k in (m.get("in_reply_to"), m.get("root")):
            if k is not None:
                rid = store.kv_get(f"bidreq:{k}")
                if rid:
                    return rid
        return None

    def on_bid(self, m: dict) -> None:
        deal_id = self.deal_for_bid(m)
        if deal_id is None:
            return
        rec = store.get(deal_id)
        if rec and rec["data"].get("booking") and re.search(r"\bconfirm|\bbooked\b", m["body"], re.I):
            self.on_booking_mail(m)
        carrier = kit.world().carrier_by_email(m["sender"])
        raw = language.read_bid(m["sender"], m["subject"], m["body"], deal_id)
        offers = [o for o in (self.offer(x, m, carrier) for x in raw) if o is not None]
        notes = [{"from": m["sender"], "mail": m["id"], "text": m["body"][:2000]}] if not offers else []
        store.update(deal_id, lambda r: (r["status"], {
            **r["data"], "replied": r["data"].get("replied", []) + [m["sender"]],
            "offers": r["data"].get("offers", []) + [o.as_dict() for o in offers],
            "carrier_messages": r["data"].get("carrier_messages", []) + notes}))
        store.log("bids", "info", f"{m['sender']}: " + (", ".join(f"{o.carrier} {o.total}" for o in offers)
                                                        or "no price (see carrier_messages)"), run_id=deal_id)

    def offer(self, o: dict, m: dict, carrier: kit.Carrier | None) -> Offer | None:
        if not o.get("available") or o.get("total") is None:
            return None
        total = self.eur(Decimal(str(o["total"])), o.get("currency") or "EUR", None)
        if total is None:
            return None
        trucker = carrier is not None and carrier.kind == "trucker"
        days = (Decimal(str(o["pickup_hours"])) / 24).quantize(Decimal("0.001")) \
            if trucker and o.get("pickup_hours") is not None else Decimal(str(o.get("transit_days") or 0))
        # a carrier answering for itself is named as in the carrier list (its mail bid and its sheet are one
        # carrier); the rate desk names the airlines it lists
        name = carrier.name if carrier else (o.get("carrier") or m["sender"])
        return Offer("pickup" if trucker else "air", name, total, days, "email", o.get("reference"),
                     reply_mail=m["id"], email=m["sender"] if carrier else None,
                     extra={"valid_until": o.get("valid_until"), "note": o.get("note")})

    def on_ratedesk(self, m: dict) -> None:
        lane = re.search(r"\b([A-Z]{3})-([A-Z]{3})\b", m["subject"] or "")
        if not lane:
            return
        for rec in store.records("deal"):
            req = rec["data"].get("request") or {}
            if (req.get("origin"), req.get("destination")) == lane.groups() and rec["status"] in ("new", "pricing"):
                offers = [o for o in (self.offer(x, m, None) for x in language.read_bid(
                    m["sender"], m["subject"], m["body"], rec["id"])) if o is not None]
                for o in offers:
                    o.source = "ratedesk"
                store.update(rec["id"], lambda r: (r["status"], {
                    **r["data"], "replied": r["data"].get("replied", []) + [RATEDESK],
                    "offers": r["data"].get("offers", []) + [o.as_dict() for o in offers]}))

    def on_booking_mail(self, m: dict) -> None:
        text = f"{m['subject']}\n{m['body']}"
        for rec in store.records("booking"):
            b = rec["data"]
            if any(x and x in text for x in (b.get("rate_id"), b.get("team_reference"), b.get("booking_reference"))):
                ref = re.search(r"Booking\s+(\S+)\s+confirmed", m["subject"] or "", re.I)
                found = re.search(r"\b(?:booking reference|reference)\s*:?\s*([A-Z0-9][A-Z0-9-]{3,})", m["body"], re.I)
                b = {**b, "status": "confirmed", "confirmation_mail": m["id"],
                     "booking_reference": b.get("booking_reference") or (ref.group(1) if ref else None)
                     or (found.group(1) if found else None)}
                store.put(rec["id"], "booking", "confirmed", b)
                store.update(b["deal"], lambda r: (r["status"], {**r["data"], "booking": b}))
                store.log("booking", "info", f"confirmed {b.get('booking_reference')}", run_id=b["deal"])
                # news from the world for this deal: its session hears it (and decides whether the customer should)
                agent.notify(f"session-{store.get(b['deal'])['data']['root']}",
                             f"The airline confirmed the booking (their mail {m['id']}): booking reference "
                             f"{b.get('booking_reference')}. Mail:\n{m['body'][:1500]}")
                return
        store.log("booking", "info", f"confirmation not matched: {m['subject']}")

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

    # ---- tariffs -------------------------------------------------------------------------------------------

    def on_tariff(self, m: dict) -> None:
        carrier = kit.world().carrier_by_email(m["sender"])
        parts, images = [m["body"]], []
        for a in m.get("attachments") or []:
            name = (a.get("filename") or "").lower()
            try:
                raw = self.api.attachment(m["id"], a.get("id"))
                if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):  # a scanned sheet: the model looks
                    images.append(("image/png" if name.endswith(".png") else "image/jpeg", raw))
                else:
                    parts.append(f"[{a.get('filename')}]\n" + docs.text(name, raw))
            except Exception as e:
                store.log("tariff", "error", f"attachment {a.get('filename')}: {e!r}")
        out = language.read_tariff("\n\n".join(parts), run_id=f"tariff-{m['id']}", images=images or None)
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

    # ---- watcher: how the field judges us ------------------------------------------------------------------

    def watch_board(self) -> None:
        """How the field judges us, every 30 s: our verdict per request, every team's standing, the last rounds.
        Every change is kept, so we can learn from it (and the UI shows it)."""
        me, public = self.api.board_me(), self.api.board()
        store.kv_set("board_me", json.dumps(me))
        store.kv_set("board", json.dumps(public))
        snap = json.dumps({"me": me, "public": public}, sort_keys=True)
        if snap != store.kv_get("board_last"):
            store.kv_set("board_last", snap)
            store.put(f"board-{int(time.time())}", "board", "snapshot", {"me": me, "public": public, "at": time.time()})
        seen = set((store.kv_get("board_seen") or "").split(","))
        for r in me.get("requests", []):
            key = f"{r.get('round')}:{r.get('verdict')}"
            if key not in seen and r.get("verdict") not in ("open", "pending"):
                seen.add(key)
                store.log("watcher", "info", f"round {r.get('round')}: {r.get('verdict')} {r.get('reason') or ''}"[:300],
                          r)
        store.kv_set("board_seen", ",".join(sorted(x for x in seen if x)))
        anomaly.check()  # a market change, seen before failed quotes pile up (app/anomaly.py)


# ---- helpers -----------------------------------------------------------------------------------------------

def normalise(s: dict, w: kit.World) -> dict:
    """From the shipment as the agent passes it (the customer's words and units) to the facts code prices with."""
    pieces = s.get("pieces")
    kg = language.weight_kg(s.get("weight") or {}, pieces)
    cbm = language.volume_cbm(s.get("volume") or {}, s.get("dimensions") or [], pieces)
    pickup = s.get("pickup") or {}
    zone = None
    postcode = re.sub(r"\D", "", pickup.get("postcode") or "")
    if len(postcode) >= 2 and postcode[:2] in w.zones:
        zone = postcode[:2]
    if pickup and not zone and pickup.get("city"):  # "pickup in Darmstadt": that zone's area
        city = pickup["city"].strip().lower()
        zone = next((z for z, v in w.zones.items() if v["area"].lower() == city), None) or \
            next((z for z, v in w.zones.items() if city in v["area"].lower() or v["area"].lower() in city), None)
    origin = (s.get("origin_airport") or "").upper() or None
    if zone:
        origin = w.zones[zone]["airport"]  # the truck goes to its zone's airport
    dest = (s.get("destination_airport") or "").upper() or None
    missing = []
    if not origin or origin not in w.origins():
        missing.append(f"departure airport or pickup place in Germany (we fly from {', '.join(sorted(w.origins()))}; "
                       f"pickup postcodes start with {', '.join(sorted(w.zones))})")
    if pickup and (pickup.get("postcode") or pickup.get("city")) and not zone:
        missing.append("a pickup postcode inside our pickup zones")
    if not dest:
        missing.append("destination airport")
    if kg is None:
        missing.append("total weight")
    cw = pricing.chargeable(kg, cbm) if kg else None
    return {"origin": origin, "destination": dest, "weight_kg": str(kg) if kg else None,
            "volume_cbm": str(cbm.quantize(Decimal("0.001"))) if cbm else None,
            "chargeable_kg": str(cw) if cw else None, "pieces": pieces, "pickup_zone": zone,
            "pickup_postcode": pickup.get("postcode"), "ready_date": (s.get("cargo") or {}).get("ready_date"),
            "commodity": (s.get("cargo") or {}).get("commodity"), "missing": missing}


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


def _root(m: dict) -> int:
    refs = m.get("references") or []
    return refs[0] if refs else m["id"]
