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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_CEILING, Decimal
from typing import Any, Callable

from . import agent, docs, kit, language, pricing, store
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
        self.fx: dict[str, Decimal] = {}  # EUR per 1 unit of a currency, as last stated with a price
        self._last_portal = time.time()
        self._gone: dict[str, set[str]] = {}  # per deal: airlines the portal answered 404 for (to ask by mail)
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
        if self.deal_for_bid(m):
            return "bid"
        if kit.world().carrier_by_email(sender):
            # a confirmation, or news about one of our bookings (delay, change, cancellation): only from a carrier on
            # our list. A subject saying "Booking BK-... confirmed" from anyone else is what the mail claims, not who
            # sent it: with our reference and another price it would reprice the booking and the customer's total
            if re.match(r"^booking\s+\S+\s+confirmed", subject, re.I) or booking_for(f"{subject}\n{m['body']}"):
                return "booking"
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
                        "hint": "if the customer's words already say it (a city is its airport), call again with it; "
                                "otherwise ask the customer for exactly this (what is out of our service is no "
                                "question: tell them so)"}
            same = deal and deal["data"].get("request") and all(
                deal["data"]["request"].get(k) == req.get(k)
                for k in ("origin", "destination", "chargeable_kg", "pickup_zone", "volume_cbm"))
            if same and any(req.get(k) != deal["data"]["request"].get(k) for k in ("insurance", "extra_charges")):
                # the same goods, with what the customer adds to the price: no new asks, the totals follow
                store.update(deal_id, lambda r: (r["status"], {**r["data"], "request": {
                    **r["data"]["request"], "insurance": req.get("insurance"), "extra_charges": req.get("extra_charges")}}))
            if not same:
                if deal and deal["data"].get("request"):  # another shipment in this deal: its options get a new
                    store.update(deal_id, lambda r: (r["status"], {**r["data"], "option_set": r["data"].get("option_set", 0) + 1}))
                self._ask_everyone(deal_id, req)
        deal = store.get(deal_id)
        if not deal or not deal["data"].get("request"):
            if deal and deal["data"].get("asked"):  # nothing to price (a tracking thread): wait for the answers
                self._wait(deal_id, wait)
                d = store.get(deal_id)["data"]
                return {"carrier_messages": d.get("carrier_messages", []), "still_waiting_for": waiting_for(d)}
            return {"error": "no shipment yet: call get_offers with the shipment"}
        self._wait(deal_id, wait)
        return self.options(deal_id, preference)

    def _wait(self, deal_id: str, wait: float) -> None:
        end = time.time() + max(0.0, float(wait))
        while time.time() < end and waiting_for(store.get(deal_id)["data"]):
            self._retry_portal(deal_id)
            self.wait_step()

    PORTAL_RETRY = (15, 45)  # seconds between tries (the portal allows 10 rates a minute for the team), and how long a lane's portal outage is worth waiting for (round 94: it stayed down for minutes; the quote must still go out inside 2 minutes)

    def _retry_portal(self, deal_id: str) -> None:
        """The portal answered 5xx or 429 for some airlines of this request: try them again while we wait for the
        carriers (round 93: '503 The rate API is unavailable' for the two fastest airlines, which sell only there;
        quoted without them, 'too low to be right')."""
        d = store.get(deal_id)["data"]
        pr = d.get("portal_retry")
        if not pr or not pr.get("names") or time.time() < pr.get("next", 0):
            return
        if time.time() - pr["since"] > self.PORTAL_RETRY[1]:
            store.update(deal_id, lambda r: (r["status"], {**r["data"], "portal_retry": {**pr, "names": []}}))
            return
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "portal_retry": {
            **pr, "next": time.time() + self.PORTAL_RETRY[0]}}))
        cbm = Decimal(pr["cbm"]) if pr.get("cbm") else None
        got, failed = self.portal_offers(deal_id, pr["o"], pr["d"], Decimal(pr["kg"]), cbm, Decimal(pr["cw"]),
                                         only=set(pr["names"]))
        left = sorted(set(pr["names"]) & failed)
        if got:
            store.log("bids", "info", f"portal back for {', '.join(sorted({x.carrier for x in got}))}", run_id=deal_id)
        back = {x.carrier for x in got if x.source == "portal"}
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "offers": [
            o for o in r["data"]["offers"] if not (o["source"] == "portal_memory" and o["carrier"] in back)] + [
            x.as_dict() for x in got if x.source == "portal" or x.carrier not in {
                o["carrier"] for o in r["data"]["offers"] if o["source"] == "portal_memory"}],
            "portal_retry": {**r["data"].get("portal_retry", pr), "names": left}}))

    def wait_step(self) -> None:
        """While a tool waits for carriers, the loop's other threads read their replies."""
        time.sleep(0.5)

    def _ask_everyone(self, deal_id: str, req: dict) -> None:
        w = kit.world()
        o, d, cw = req["origin"], req["destination"], Decimal(req["chargeable_kg"])
        kg, cbm = Decimal(req["weight_kg"]), Decimal(req["volume_cbm"]) if req["volume_cbm"] else None
        offers: list[Offer] = []
        for lane in w.sheet(o, d, on=_day(req.get("ready_date"))):  # known prices, valid on the ready date
            total, billed = pricing.sheet_price(lane, kg, cbm)
            offers.append(Offer("air", lane["airline"], total, Decimal(lane["transit_days"]), "sheet", None, billed))
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "request": req, "offers": [x.as_dict() for x in offers],
                                                       "asked": {}, "replied": [], "declined": [], "asked_at": time.time()}))
        asked: dict[str, str] = {}
        not_asked: list[dict] = []
        with_sheet = {l["airline"] for l in w.sheet_lanes}
        for c in w.email_airlines(o, d):  # carriers that quote by mail
            told = lanes_told(c.email)
            if told is not None and f"{o}-{d}" not in told["lanes"]:
                not_asked.append({"carrier": c.name, "email": c.email,
                                  "why": f"told us at {time.strftime('%H:%M', time.localtime(told['at']))} "
                                         f"the lanes it flies, {o}-{d} not among them"})
                continue
            weights = [next((x.billed_kg for x in offers if x.carrier == c.name), cw)]
            if c.name not in with_sheet:  # breaks unknown: billing at the next break up may be the cheaper price
                weights += pricing.breaks_to_try(cw)
            for wt in weights:
                self._ask(asked, deal_id, c, self.ask_airline, deal_id, c, o, d, wt, cbm, req)
        if req["pickup_zone"]:
            for c in w.truckers(req["pickup_zone"]):
                self._ask(asked, deal_id, c, self.ask_trucker, deal_id, c, req)
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "asked": {**r["data"]["asked"], **asked},
                                                       "not_asked": not_asked}))
        self._gone.pop(deal_id, None)
        portal, failed = self.portal_offers(deal_id, o, d, kg, cbm, cw)
        fallback: list = []  # mails to portal airlines while the portal fails: tried, never awaited (round 94)
        # airlines that may have moved from the portal to mail: off the portal for this lane, or a 404 for it
        for c in w.portal_airlines_off_lane(o, d) + [x for x in (w.carrier_by_name(n) for n in
                                                                 self._gone.pop(deal_id, set())) if x]:
            told = lanes_told(c.email)
            if c.email in asked.values() or (told is not None and f"{o}-{d}" not in told["lanes"]):
                continue
            self._ask(asked, deal_id, c, self.ask_airline, deal_id, c, o, d, cw, cbm, req)
            fallback.append(next(reversed(asked)) if asked else None)
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "portal_retry": {
            "o": o, "d": d, "kg": str(kg), "cbm": str(cbm) if cbm else None, "cw": str(cw), "names": sorted(failed),
            "since": time.time(), "next": time.time() + self.PORTAL_RETRY[0]}}))
        for name in failed:  # portal down or over the limit for this airline: ask the airline by mail, also at the
            c = w.carrier_by_name(name)  # break above when it can bill cheaper there (as for every mail airline)
            if c and c.email not in asked.values():
                code = next((a["code"] for a in w.portal.get((o, d), []) if a["name"] == name), None)
                breaks = w.brackets.get(code or "", [])
                nb = pricing.next_break(breaks, cw)
                above = ([nb] if nb is not None and nb / cw < Decimal("1.5") else []) if breaks \
                    else pricing.breaks_to_try(cw)
                for wt in [cw] + above:
                    self._ask(asked, deal_id, c, self.ask_airline, deal_id, c, o, d, wt, cbm, req)
                    fallback.append(next(reversed(asked)) if asked else None)
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "asked": {**r["data"]["asked"], **asked},
                                                       "fallback_asks": [x for x in fallback if x],
                                                       "offers": r["data"]["offers"] + [x.as_dict() for x in portal]}))
        store.log("bids", "info", f"{o}-{d} {cw} kg: {len(offers) + len(portal)} prices now, asked {len(asked)} by mail",
                  run_id=deal_id)

    @staticmethod
    def _ask(asked: dict, deal_id: str, c: kit.Carrier, ask, *args) -> None:
        """One carrier asked; a mail that cannot go out (5U's limit, a 5xx) is logged and the others, the portal
        included, are still asked: one failed send must not cost the whole price collection."""
        try:
            asked[str(ask(*args))] = c.email
        except Exception as e:
            store.log("bids", "error", f"could not ask {c.name}: {e!r}"[:300], run_id=deal_id)

    def options(self, deal_id: str, preference: str) -> dict:
        """The priced options as the agent sees them. Every number here is computed by code."""
        d = store.get(deal_id)["data"]
        req = d["request"]
        declined = {n.lower() for n in d.get("declined", [])}
        offers = [x for x in (Offer.of(x) for x in d.get("offers", []))
                  if not (x.source == "sheet" and x.carrier.lower() in declined)]
        air = sorted(pricing.best_by_carrier([x for x in offers if x.leg == "air"]), key=lambda o: o.total)
        pickups = sorted(pricing.best_by_carrier([x for x in offers if x.leg == "pickup"]), key=lambda o: o.total)
        needs_pickup = bool(req["pickup_zone"])
        premium = pricing.insurance_premium(req.get("insurance"))  # part of the all-in total when they ask for it
        # an option id names one option for the life of the deal: a changed or second shipment prices as B1, B2...,
        # and what was quoted before stays bookable under its own id (Sam's probe: two shipments in one mail, the
        # second pricing renamed A1 and book("A1") would have booked it)
        letter = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[min(int(d.get("option_set", 0)), 25)]
        table: dict[str, dict] = {}
        rows = []
        variants = pickup_variants(pickups, preference) if needs_pickup else [("", None)]
        for i, a in enumerate(air, 1):
            for tag, p in variants:
                if needs_pickup and p is None:
                    continue
                oid = f"{letter}{i}{tag}"
                freight = a.total + (p.total if p else 0)
                extra, skipped = pricing.extra_charges(req.get("extra_charges"), freight, Decimal(req["chargeable_kg"]))
                total = pricing.money(freight + (premium or 0) + extra)
                # the shipment this option prices: a deal can price several (round 89: GRU and TLV in one mail),
                # and the booking must carry the route and goods of the option booked, not of the last pricing
                table[oid] = {"air": a.as_dict(), "pickup": p.as_dict() if p else None, "total": str(total),
                              "insurance": str(premium) if premium is not None else None,
                              "extra_charges": str(extra) if req.get("extra_charges") else None,
                              "total_text": pricing.fmt(total), "request": {k: v for k, v in req.items() if k != "missing"}}
                _, leaves, arrives = pricing.schedule(req.get("ready_date"), float(p.days) * 24 if p else 0, a.days)
                rows.append({"option": oid, "airline": a.carrier, "transit_days": float(a.days),
                             "pickup": {"trucker": p.carrier, "pickup_hours": round(float(p.days) * 24, 1)} if p else None,
                             "estimated_departure": leaves.strftime(pricing.DATE),
                             "estimated_arrival": arrives.strftime(pricing.DATE),
                             "total": pricing.fmt(total), "source": a.source, "bookable_reference": a.rate_id,
                             "billed_kg": float(a.billed_kg) if a.billed_kg is not None else None,
                             "carrier_note": (a.extra or {}).get("note")})
        rec = {}
        for pref in ("cheapest", "fastest", "balanced"):
            cand = [Offer("air", k, Decimal(v["total"]),
                          Decimal(v["air"]["days"]) + (Decimal(v["pickup"]["days"]) if v["pickup"] else 0), "x")
                    for k, v in table.items()]
            best = pricing.pick(cand, pref if pref != "balanced" else "unspecified", settings.balance_rule)
            if best:
                rec[pref] = best.carrier
        store.update(deal_id, lambda r: (r["status"], {**r["data"], "options": {
            **{k: v for k, v in (r["data"].get("options") or {}).items() if not k.startswith(letter)}, **table}}))
        waiting = waiting_for(d)
        pref_key = preference if preference in ("cheapest", "fastest") else settings.unspecified_rule
        result = {"shipment": {k: req[k] for k in ("origin", "destination", "weight_kg", "volume_cbm", "chargeable_kg",
                                                 "pieces", "pickup_zone", "pickup_postcode")},
                "options": rows, "recommended": rec.get(pref_key), "recommended_for": pref_key,
                "recommended_by_preference": rec,
                "pickup_alternatives": [{"trucker": p.carrier, "total": pricing.fmt(p.total),
                                         "pickup_hours": round(float(p.days) * 24, 1)} for p in pickups],
                "still_waiting_for": waiting,
                # the clock the customer and 5U read: the quote scores best inside 120 s of their mail
                "seconds_since_request": _since(d.get("received_at")),
                # answers that change the picture: a carrier we had a price for says no, or a carrier asks back
                "carriers_without_price": [{"from": c["from"], "mail": c["mail"], "says": c["text"][:400]}
                                           for c in d.get("carrier_messages", [])
                                           if c.get("had_sheet_price") or c.get("declined") is False][-5:]}
        if req.get("insurance"):
            result["insurance"] = ({"premium": pricing.fmt(premium), "included_in_every_total": True} if premium
                                   is not None else {"included_in_every_total": False, "why": "the goods value is "
                                   "not in EUR or a term is missing: ask, never compute it yourself"})
        if req.get("extra_charges"):
            _, skipped = pricing.extra_charges(req.get("extra_charges"), Decimal(0), Decimal(req["chargeable_kg"]))
            result["extra_charges"] = {"included_in_every_total": [c.get("label") for c in req["extra_charges"]
                                                                   if not any(str(c.get("label")) in x for x in skipped)],
                                       "not_added": skipped or None}
        if d.get("not_asked"):  # the agent can still ask one of them (mail_carrier) when it judges it useful
            result["not_asked"] = [{"carrier": x["carrier"], "email": x["email"], "why": x["why"]}
                                   for x in d["not_asked"]]
        if not rows:  # nothing to quote: say why, with everything the carriers wrote (round 15 showed neither)
            result["no_options_because"] = ("no trucker has priced the pickup" if needs_pickup and air
                                            else "no airline has priced this route")
            result["carriers_without_price"] = [{"from": c["from"], "mail": c["mail"], "says": c["text"][:300]}
                                                for c in d.get("carrier_messages", [])][-12:]
        return result

    def ask_airline(self, deal_id: str, c: kit.Carrier, o: str, d: str, billed: Decimal, cbm: Decimal | None,
                    req: dict) -> int:
        # labelled lines: the carriers' desks read "Total weight: N kg" (live: "320 kg chargeable" was not read)
        body = (f"Hello {c.name} team,\n\nplease quote air freight for this shipment:\n"
                f"Route: {o} to {d}\nTotal weight: {kg_text(billed)} kg\n"
                + (f"Volume: {cbm:.2f} cbm\n" if cbm else "")
                + f"Pieces: {req.get('pieces') or 1}\nCargo: general cargo\n"
                f"Ready: {req.get('ready_date') or 'now'}\n\n"
                "Please send your all-in total, currency, transit time, rate reference and validity.\n\n"
                f"Thanks,\n{settings.persona}, {settings.company}")
        mid = self.mail_carrier(deal_id, c.email, f"Rate request {o}-{d} {kg_text(billed)} kg", body)
        store.kv_set(f"bidweight:{mid}", kg_text(billed))
        return mid

    def ask_trucker(self, deal_id: str, c: kit.Carrier, req: dict) -> int:
        z = kit.world().zones.get(req["pickup_zone"], {})
        postcode = req.get("pickup_postcode") or kit.ZONE_POSTCODE.get(req["pickup_zone"], "")  # a town: its postcode
        body = (f"Hello {c.name} team,\n\nplease quote a pickup from {postcode} "
                f"{z.get('area', '')} (zone {req['pickup_zone']}) to {z.get('airport', req['origin'])} airport.\n"
                f"Total weight: {kg_text(Decimal(req['weight_kg']))} kg\n"
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
                      cw: Decimal, only: set[str] | None = None) -> tuple[list[Offer], set[str]]:
        """Portal prices at the chargeable weight and at the next break; airlines the portal failed for."""
        w, out, failed = kit.world(), [], set()
        for a in w.portal.get((o, d), []):
            if only is not None and a["name"] not in only:
                continue
            weights = [kg]
            nb = pricing.next_break(w.brackets.get(a["code"], []), cw)
            if nb is not None and nb / cw < Decimal("1.5"):
                weights.append(nb)  # billing at the next break is often cheaper (rates fall < 1.5x per break)
            for wt in weights:
                r = self.api.rate(o, d, a["code"], wt, cbm)
                if r.get("error"):
                    store.log("bids", "error", f"portal {a['code']} {o}-{d}: {r['status']} {r['detail']}"[:300],
                              run_id=deal_id)
                    if r["status"] == 404 and wt == kg:  # not on the portal for this lane (any more): by mail
                        self._gone.setdefault(deal_id, set()).add(a["name"])
                        self._last_portal = 0  # the lane list is stale: read it again now
                    if r["status"] in (429, 500, 502, 503, 504):
                        if wt == kg:
                            failed.add(a["name"])
                        mem = remembered_offer(a, o, d, cw if wt == kg else Decimal(wt), w.brackets.get(a["code"]))
                        if mem:  # the portal is down: this airline's own rate on this lane, from earlier tonight
                            out.append(mem)
                    continue
                total = self.eur(Decimal(r["total"]), r["currency"], r.get("fx_eur_per_usd"))
                if total is None:
                    continue
                remember_rate(a, o, d, total, Decimal(r["chargeable_weight_kg"]), r["transit_days"],
                              w.brackets.get(a["code"]))
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
        air, req = opt["air"], opt.get("request") or d["request"]
        # one deal can book more than one shipment (round 89: GRU now, TLV "later"): each booking keeps its own
        # reference and record, the first as SM-<root>, the next as SM-<root>-2; booking an option again reuses its own
        done = [b for b in (d.get("bookings") or ([d["booking"]] if d.get("booking") else [])) if b.get("status") != "failed"]
        mine = next((b for b in done if b.get("option") == option_id), None)
        ref = mine["team_reference"] if mine else f"SM-{d['root']}" + (f"-{len(done) + 1}" if done else "")
        status, body = 0, {}
        if not air.get("rate_id") and air.get("source") == "portal_memory":  # priced while the portal was down
            r = self.api.rate(req["origin"], req["destination"], air["extra"]["code"],
                              air["extra"].get("weight") or req["weight_kg"], req.get("volume_cbm"))
            if not r.get("error"):
                air = {**air, "rate_id": r["rate_id"]}
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
                   "pieces": req.get("pieces"), "rate_id": air.get("rate_id"),
                   # everything in the all-in total besides the flight: pickup, insurance, charges they asked for
                   "others": str(pricing.money(Decimal(str(opt["total"])) - Decimal(str(air["total"]))))}
        if status in (200, 201):
            booking.update(booking_reference=body.get("booking_reference"), status="booked", via="portal",
                           price=body.get("price"), currency=body.get("currency"), note=body.get("note"))
            # the airline's booking price is what it charges, also when it is not the rate we quoted (round 48:
            # quoted 5655.55, booked at 6221.11): the all-in total follows it, and the change is stated plainly
            try:
                booked_air = self.eur(Decimal(str(body["price"])), body.get("currency") or "EUR", None)
            except Exception:
                booked_air = None
            if booked_air is not None and pricing.money(booked_air) != pricing.money(Decimal(str(air["total"]))):
                now = booked_air + Decimal(booking["others"])
                booking.update(amount=pricing.fmt(now), quoted_amount=opt["total_text"],
                               price_changed={"quoted": opt["total_text"], "booked": pricing.fmt(now)})
        elif air.get("email") or kit.world().carrier_by_name(air["carrier"]):  # by mail with the airline
            air = {**air, "email": air.get("email") or kit.world().carrier_by_name(air["carrier"]).email}
            text = (f"Hello,\n\nwe would like to book your offer {air.get('rate_id') or ''} ({booking['route']}, "
                    f"{kg_text(Decimal(air.get('billed_kg') or req['weight_kg']))} kg). Our reference: {ref}.\n\n"
                    f"Thanks,\n{settings.persona}, {settings.company}")
            asked = self.mail_carrier(deal_id, air["email"], f"Booking {air.get('rate_id') or ref}", text,
                                      in_reply_to=air.get("reply_mail"))
            booking.update(status="requested", via="email", request_mail=asked,
                           portal_answer={"status": status, "body": body})
        else:
            booking.update(status="failed", via="portal", error={"status": status, "body": body})
        store.put(f"booking-{ref[3:]}", "booking", booking["status"], booking)
        if booking["status"] != "failed":
            store.update(deal_id, lambda r: ("booked", {**r["data"], "booking": booking, "bookings": [
                b for b in done if b.get("team_reference") != ref] + [booking]}))
        return booking

    def cancel_booking(self, deal_id: str, booking_reference: str) -> dict:
        """Cancel one of this deal's bookings with 5U (DELETE on the portal, for portal and mail bookings alike). The
        booking stays in the register as cancelled, so the CRM and tracking say so (round 88: six mails to an
        airline's quote desk, never cancelled, -20)."""
        d = store.get(deal_id)["data"]
        mine = [b for b in (d.get("bookings") or ([d["booking"]] if d.get("booking") else []))
                if b.get("booking_reference") == booking_reference]
        if not mine:
            refs = [b.get("booking_reference") for b in (d.get("bookings") or [d.get("booking") or {}])]
            return {"error": f"{booking_reference} is not a booking of this deal", "bookings": refs}
        status, body = self.api.cancel_booking(booking_reference)
        store.log("booking", "info", f"cancel {booking_reference}: {status}", body, run_id=deal_id)
        if status != 200:
            return {"error": f"5U answered {status}", "detail": body}
        key = f"booking-{mine[0]['team_reference'][3:]}"
        b = {**(store.get(key) or {"data": mine[0]})["data"], "status": "cancelled", "cancelled_at": time.time()}
        store.put(key, "booking", "cancelled", b)
        store.update(deal_id, lambda r: ("cancelled" if all(
            x.get("booking_reference") == booking_reference or x.get("status") == "cancelled"
            for x in (r["data"].get("bookings") or [r["data"].get("booking") or {}])) else r["status"], {
            **r["data"], "booking": b if (r["data"].get("booking") or {}).get("booking_reference") == booking_reference
            else r["data"].get("booking"),
            "bookings": [b if x.get("booking_reference") == booking_reference else x
                         for x in (r["data"].get("bookings") or [])]}))
        return {"cancelled": booking_reference, "status": "cancelled", "note": "5U no longer counts it as booked; "
                "the airline needs no mail"}

    # ---- carrier mail (system tasks, no agent) -------------------------------------------------------------

    def deal_for_bid(self, m: dict) -> str | None:
        for k in (m.get("in_reply_to"), m.get("root")):
            if k is not None:
                rid = store.kv_get(f"bidreq:{k}")
                if rid:
                    return rid
        return None

    def with_attachments(self, m: dict) -> dict:
        """A carrier's mail as a person reads it: the body and what its attachments say (round 63: the truckers
        sent their prices as a PDF, a Word letter and a voice message, and a body-only reader saw no price)."""
        parts = [m["body"] or ""]
        for a in m.get("attachments") or []:
            try:
                parts.append(f"[attachment {a.get('filename')}]\n" + docs.text(
                    a.get("filename", ""), self.api.attachment(m["id"], a.get("id")), run_id=f"deal-{m.get('root')}"))
            except Exception as e:
                parts.append(f"[attachment {a.get('filename')}: could not be read: {e!r}]")
        if len(parts) > 1:  # kept, so the team sees in the UI what we read from each file (a transcript, a scan)
            store.kv_set(f"read:{m['id']}", "\n\n".join(parts[1:]))
        return {**m, "body": "\n\n".join(parts)} if len(parts) > 1 else m

    def on_bid(self, m: dict) -> None:
        deal_id = self.deal_for_bid(m)
        if deal_id is None:
            return
        m = self.with_attachments(m)
        rec = store.get(deal_id)
        booked = (rec or {}).get("data", {}).get("booking") or {}
        answers_us = m.get("in_reply_to") and (m["in_reply_to"] == booked.get("request_mail")
                                               or store.kv_get(f"agentmail:{m['in_reply_to']}"))
        if booked and (is_confirmation(m) or answers_us):
            # the airline answering our booking (its confirmation, its reply to our booking mail, or to a mail the
            # agent wrote after it, such as a cancellation) is booking news, not an offer: round 51's "thank you for
            # your booking ... Price: 4466.52" became a 0-day option; Sam's probe (Sun 00:30) lost a cancellation
            self.on_booking_mail(m, store.get(f"booking-{rec['data']['root']}"))
            return
        carrier = kit.world().carrier_by_email(m["sender"])
        told = re.search(r"\bwe fly\b([^\n]*)", m["body"], re.I)  # "We fly CGN-DEL, FRA-JFK, ..." in a decline
        if told and carrier:
            lanes = re.findall(r"\b[A-Z]{3}-[A-Z]{3}\b", told.group(1))
            if lanes:
                store.kv_set(f"lanes:{carrier.email}", json.dumps({"lanes": lanes, "at": time.time()}))
        raw = language.read_bid(m["sender"], m["subject"], m["body"], deal_id)
        if not all(read_in_mail(x, m["body"]) for x in raw):  # an amount the mail never wrote is a misread
            store.log("bids", "error", f"{m['sender']}: amount not in the mail, reading it again", {"read": raw},
                      run_id=deal_id)
            raw = language.read_bid(m["sender"], m["subject"], m["body"], deal_id)
            kept = []
            for x in raw:
                if not read_in_mail(x, m["body"]) and read_in_mail({**x, "total": None}, m["body"]) \
                        and x.get("rate_per_kg") is not None:
                    x = {**x, "total": None}  # the rate is in the mail: code computes the total from the parts
                if read_in_mail(x, m["body"]):
                    kept.append(x)
                else:
                    store.log("bids", "error", f"{m['sender']}: amount still not in the mail, offer left out",
                              {"read": x}, run_id=deal_id)
            raw = kept
        offers = [o for o in (self.offer(x, m, carrier) for x in raw) if o is not None]
        # what a carrier says now beats its sheet, also when it says no (lane closed, flights suspended): its
        # sheet price is no longer on offer. A carrier that only asks back for facts keeps it.
        said_no = bool(carrier and not offers and any(x.get("available") is False for x in raw))
        had_sheet = bool(carrier and rec and any(o["source"] == "sheet" and o["carrier"] == carrier.name
                                                 for o in rec["data"].get("offers", [])))
        notes = [{"from": m["sender"], "mail": m["id"], "text": m["body"][:2000], "declined": said_no,
                  "had_sheet_price": had_sheet}] if not offers else []
        store.update(deal_id, lambda r: (r["status"], {
            **r["data"], "replied": r["data"].get("replied", []) + [m["sender"]],
            "offers": r["data"].get("offers", []) + [o.as_dict() for o in offers],
            "declined": sorted(set(r["data"].get("declined", []) + ([carrier.name] if said_no else []))),
            "carrier_messages": r["data"].get("carrier_messages", []) + notes}))
        store.log("bids", "info", f"{m['sender']}: " + (", ".join(f"{o.carrier} {o.total}" for o in offers)
                                                        or "no price (see carrier_messages)"), run_id=deal_id)

    def offer(self, o: dict, m: dict, carrier: kit.Carrier | None) -> Offer | None:
        if not o.get("available"):
            return None
        amount = Decimal(str(o["total"])) if o.get("total") is not None else self.total_from_parts(o, m)
        if amount is None:
            return None
        total = self.eur(amount, o.get("currency") or "EUR", o.get("fx_eur_per_unit"))
        if total is None:
            return None
        trucker = carrier is not None and carrier.kind == "trucker"
        days = language.days(o.get("time_value"), o.get("time_unit"))
        if days is None and trucker:  # a trucker sends one offer: the time its mail states is that offer's
            days = language.time_in(m["body"])
        days = days or Decimal(0)
        # a carrier answering for itself is named as in the carrier list (its mail bid and its sheet are one
        # carrier); the rate desk names the airlines it lists
        name = carrier.name if carrier else (o.get("carrier") or m["sender"])
        return Offer("pickup" if trucker else "air", name, total, days, "email", clean_reference(o.get("reference")),
                     reply_mail=m["id"], email=m["sender"] if carrier else None,
                     extra={"valid_until": o.get("valid_until"), "note": o.get("note")})

    def total_from_parts(self, o: dict, m: dict) -> Decimal | None:
        """A carrier that quotes per kg, or itemised, without a total: the total for the weight it bills (or the
        weight we asked it for), by the same rule as the sheets: minimum on the freight, surcharges per kg, fees."""
        rate = o.get("rate_per_kg")
        if rate is None:
            return None
        kg = o.get("billed_kg") or store.kv_get(f"bidweight:{m.get('in_reply_to')}")
        if kg is None:
            return None
        kg = Decimal(str(kg))
        freight = max(Decimal(str(o.get("minimum_charge") or 0)), Decimal(str(rate)) * kg)
        total = freight + Decimal(str(o.get("surcharges_per_kg") or 0)) * kg + Decimal(str(o.get("fixed_fees") or 0))
        store.log("bids", "info", f"{m['sender']}: total computed from parts {total:.2f} for {kg} kg", o)
        return pricing.money(total)

    def on_ratedesk(self, m: dict) -> None:
        lane = re.search(r"\b([A-Z]{3})-([A-Z]{3})\b", m["subject"] or "")
        if not lane:
            return
        m = self.with_attachments(m)
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

    def on_booking_mail(self, m: dict, rec: dict | None = None) -> None:
        """An airline writes about one of our bookings: its confirmation, or news after it (a delay, a change, a
        cancellation). Its word goes on the booking, where crm and tracking read it; the deal's session hears it,
        unless it only confirms exactly what we booked."""
        text = f"{m['subject']}\n{m['body']}"
        rec = rec or booking_for(text)
        if rec is None:
            store.log("booking", "info", f"airline mail not matched to a booking: {m['subject']}")
            return
        b = rec["data"]
        confirmation = is_confirmation(m)
        ref = re.search(r"Booking\s+(\S+)\s+confirmed", m["subject"] or "", re.I)
        found = re.search(r"\b(?:booking reference|reference)\s*:?\s*([A-Z0-9][A-Z0-9-]{3,})", m["body"], re.I)
        b = {**b, "booking_reference": b.get("booking_reference") or (ref.group(1) if ref else None)
             or (found.group(1) if found else None)}
        if confirmation:
            b = {**b, "status": "confirmed", "confirmation_mail": m["id"], "confirmation_text": m["body"][:800]}
        else:  # the airline's latest word on this shipment: tracking answers start from it
            b = {**b, "carrier_status": {"text": m["body"][:1500], "at": m.get("received_at"), "mail": m["id"]}}
        # what the airline's price means for the customer's total, by code: its mail prices the flight, our total
        # includes the pickup (round 51 told a customer 4466.52 'rather than the quoted 4659.12': the same price)
        b, facts, changed = price_in_airline_mail(b, m["body"], confirmation)
        store.put(rec["id"], "booking", b.get("status", rec["status"]), b)
        store.update(b["deal"], lambda r: (r["status"], {**r["data"], "booking": b}))
        store.log("booking", "info", (f"confirmed {b.get('booking_reference')}" if confirmation else
                                      f"airline news on {b.get('booking_reference')}: {m['subject']}")
                  + (f" ({facts})" if changed else ""), run_id=b["deal"])
        if confirmation and not changed and confirmation_matches(b, text):  # same reference, same price: no news
            store.log("booking", "info", f"{b.get('booking_reference')}: the airline's confirmation matches "
                      "the booking, the session is not woken", run_id=b["deal"])
            return
        # news from the world for this deal: its session hears it (and decides whether the customer should)
        what = "confirmed the booking" if confirmation else "wrote about the booking"
        agent.notify(f"session-{store.get(b['deal'])['data']['root']}",
                     f"The airline {what} (their mail {m['id']}): booking reference {b.get('booking_reference')}. "
                     f"{facts}\nMail:\n{m['body'][:1500]}")

    def eur(self, amount: Decimal, currency: str, fx: Any) -> Decimal | None:
        total = pricing.to_eur(amount, currency, fx, self.fx)
        if total is None:
            store.log("bids", "error", f"cannot convert {amount} {currency} to EUR: no exchange rate seen")
        return total

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
            kit.add_sheet(airline, lanes, f"mail {m['id']}", _day(out.get("valid_from")), _day(out.get("valid_to")))
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
            rnd = r.get("round_no", r.get("round"))
            key = f"{rnd}:{r.get('verdict')}"
            if key not in seen and r.get("verdict") not in ("open", "pending"):
                seen.add(key)
                store.log("watcher", "info", f"round {rnd}: {r.get('verdict')} {r.get('reason') or ''}"[:300], r)
        store.kv_set("board_seen", ",".join(sorted(x for x in seen if x)))


# ---- helpers -----------------------------------------------------------------------------------------------

def _since(iso: str | None) -> int | None:
    from datetime import datetime
    try:
        return round(time.time() - datetime.fromisoformat(str(iso)).timestamp())
    except (TypeError, ValueError):
        return None


def _break_of(breaks: list | None, kg: Decimal) -> int | None:
    return max((int(b) for b in breaks if Decimal(b) <= kg), default=None) if breaks else None


def remember_rate(a: dict, o: str, d: str, total: Decimal, billed: Decimal, days, breaks: list | None) -> None:
    """A portal price is a rate per kg for its airline, lane and weight break (stable all night: Fjordline DUS-JFK
    2.40 at 15:13 and at 21:53). Kept, so an outage of the rate API can still be priced (rounds 93-94)."""
    lower = _break_of(breaks, billed)
    if lower is None or not billed:
        return
    store.kv_set(f"portalrate:{a['code']}:{o}-{d}:{lower}", json.dumps(
        {"per_kg": str((total / billed).quantize(Decimal("0.0001"))), "days": str(days), "name": a["name"],
         "at": time.time()}))


def remembered_offer(a: dict, o: str, d: str, billed: Decimal, breaks: list | None) -> Offer | None:
    """This airline's own portal rate on this lane in this weight break, as last seen: a price by code while the
    rate API is down, marked as such, and booked at a fresh rate when the portal answers again."""
    lower = _break_of(breaks, billed)
    raw = store.kv_get(f"portalrate:{a['code']}:{o}-{d}:{lower}") if lower is not None else None
    if not raw:
        return None
    m = json.loads(raw)
    seen = time.strftime("%H:%M", time.localtime(m["at"]))
    return Offer("air", a["name"], pricing.money(Decimal(m["per_kg"]) * billed), Decimal(m["days"]), "portal_memory",
                 None, billed, extra={"code": a["code"], "weight": str(billed), "remembered_at": seen,
                                      "note": f"portal rate API unavailable: priced from this airline's own portal "
                                              f"rate on this lane and weight break, seen at {seen}; booked at a "
                                              f"fresh rate when the portal answers"})


def waiting_for(d: dict) -> list[str]:
    """Carriers that still owe an answer. Counted per request mail: a carrier asked at two weights answers twice."""
    fallback = set(d.get("fallback_asks") or [])  # portal airlines mailed during an outage answer no mail
    asked = Counter(e for mid, e in d.get("asked", {}).items() if mid not in fallback)
    replied = Counter(d.get("replied", []))
    owed = sorted(email for email, n in asked.items() if replied[email] < n)
    pr = d.get("portal_retry") or {}
    if pr.get("names") and time.time() - pr.get("since", 0) <= Forwarder.PORTAL_RETRY[1]:
        owed += [f"portal: {n}" for n in pr["names"]]  # a portal outage is waited out, like a carrier's answer
    return owed


def pickup_variants(pickups: list[Offer], preference: str = "cheapest") -> list[tuple[str, Offer | None]]:
    """The one trucker an option carries, by PICKUP_RULE (docs/challenges/5u-facts.md).
    asked: the fastest when the customer asked for fastest (round 1: full accuracy), else the cheapest.
    cheapest: always the cheapest. balanced: always the 50/50 pick (BALANCE_RULE).
    One variant only: with two on the table the agent took the fast trucker for a "cheapest" request because the
    goods were "ready tomorrow 9:00" (stress test m08, 10.9 % over the best price)."""
    if not pickups:
        return [("", None)]
    if settings.pickup_rule == "balanced":
        return [("", pricing.balanced(pickups, settings.balance_rule))]
    if settings.pickup_rule == "asked" and preference == "fastest":
        return [("", pricing.pick(pickups, "fastest"))]
    return [("", pricing.pick(pickups, "cheapest"))]


def normalise(s: dict, w: kit.World) -> dict:
    """From the shipment as the agent passes it (the customer's words and units) to the facts code prices with."""
    pieces, kg, cbm = _goods(s)
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
    dest = kit.destination_code(s.get("destination_airport"))  # a city name is its airport in our network
    missing = []
    if pickup and (postcode or pickup.get("city")) and not zone:
        missing.append(f"a pickup postcode or town inside our pickup zones (postcodes start with "
                       f"{', '.join(sorted(w.zones))})")
    elif pickup and not zone:  # a pickup asked for, no place given at all (rounds 15-18)
        missing.append("where to collect: the pickup postcode, or at least the town")
    # A town is enough: it is its zone, and the zone prices the truck (round 20: "All I have is Augsburg").
    ours = ', '.join(sorted(w.origins()))
    if origin and origin not in w.origins() and not zone and not missing and dest in w.origins():
        # an import (Sam's probe, Sun 00:30: ORD to FRA was answered "which German departure airport?")
        missing.append(f"out of our service: {origin} to {dest} flies into Germany, and we are an export desk "
                       f"(air freight out of Germany, from {ours}). Not a question for the customer: tell them "
                       f"plainly that we do not offer it")
    elif origin and origin not in w.origins() and not zone and not missing:
        missing.append(f"{origin} is not one of our departure airports: we fly out of Germany only, from {ours}, "
                       f"or collect in our pickup zones (postcodes start with {', '.join(sorted(w.zones))}). A "
                       f"shipment that starts abroad is a service we do not offer: say so; ask only if they may have "
                       f"meant a German airport or a pickup in Germany")
    elif (not origin or origin not in w.origins()) and not missing:
        missing.append(f"departure airport or pickup place in Germany (we fly from {ours}; "
                       f"pickup postcodes start with {', '.join(sorted(w.zones))})")
    if not dest:
        missing.append("destination airport (we fly to: " + ", ".join(
            f"{c} {n.split(' / ')[0]}" for c, n in kit.DESTINATIONS.items()) + ")")
    odd = language.unknown_units(s.get("lots") or [])
    if odd:  # never guessed; the agent passes the same unit under a name we know (it never converts)
        missing.append("units we do not know: " + ", ".join(odd) + "; pass them again as kg, lb or t (weight), "
                       "cbm, cft or l (volume), cm, mm, in or ft (dimensions), as the customer meant them")
    elif kg is None:
        missing.append("total weight")
    cw = pricing.chargeable(kg, cbm) if kg else None
    return {"origin": origin, "destination": dest, "weight_kg": str(kg) if kg else None,
            # never rounded down: a rate for less volume bills less than the shipment weighs, and 5U does not count
            # that booking (round 62: lots summed to 9.3444 cbm, the portal got 9.344 and priced 1560.448 kg of
            # 1560.5148; accuracy 44.97, booked False, tracking 0)
            "volume_cbm": f"{cbm.quantize(Decimal('0.000001'), rounding=ROUND_CEILING).normalize():f}" if cbm else None,
            "chargeable_kg": str(cw) if cw else None, "pieces": pieces, "pickup_zone": zone,
            # the ready date as a date, however the customer wrote it (round 65: "24 November 2026" reached the
            # schedule as text, the dates fell back to today, and the agent told the customer to check the timing)
            "pickup_postcode": pickup.get("postcode"),
            "ready_date": _day((s.get("cargo") or {}).get("ready_date")) or (s.get("cargo") or {}).get("ready_date"),
            "commodity": (s.get("cargo") or {}).get("commodity"), "missing": missing,
            "insurance": s.get("insurance") or None, "extra_charges": s.get("extra_charges") or None}


def _goods(s: dict) -> tuple[int | None, Decimal | None, Decimal | None]:
    """Pieces, gross kg and cbm of the whole consignment, added up in code from the lots as written (a total
    weight for one lot, a weight per piece for another, dimensions per piece for a third)."""
    lots = s.get("lots")
    if not lots:  # a shipment written flat (older sessions, tests)
        lots = [{"pieces": s.get("pieces"), "weight": s.get("weight"), "volume": s.get("volume"),
                 "dimensions": None, "_dims": s.get("dimensions") or []}]
    pieces, kg, cbm, unknown = 0, Decimal(0), Decimal(0), False
    for lot in lots:
        n = lot.get("pieces")
        w = language.weight_kg(lot.get("weight") or {}, n)
        if w is None:
            unknown = True
        else:
            kg += w
        dims = lot.get("_dims") or ([{**lot["dimensions"], "count": n or 1}] if lot.get("dimensions") else [])
        v = language.volume_cbm(lot.get("volume") or {}, dims, n)
        cbm += v or 0
        pieces += n or 0
    return pieces or None, (None if unknown or not kg else kg), (cbm or None)


def _day(text: Any) -> str | None:
    """'2026-12-01', '01.12.2026', '1 Dec 2026' -> '2026-12-01'; anything else -> None."""
    from datetime import datetime
    t = str(text or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(t[:len(t)], fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(t[:10]).date().isoformat()
    except ValueError:
        pass
    # said relative to today ("ready Monday", "tomorrow", "24 November" without a year): the next such day
    from datetime import date, timedelta
    today, low = date.today(), t.lower()
    if low in ("today", "now", "asap", "immediately", "heute", "sofort"):
        return today.isoformat()
    if low in ("tomorrow", "morgen"):
        return (today + timedelta(days=1)).isoformat()
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    word = re.sub(r"^(?:next|this|on)\s+", "", low)
    if word in names:
        return (today + timedelta(days=(names.index(word) - today.weekday() - 1) % 7 + 1)).isoformat()
    for fmt in ("%d %B", "%d %b", "%B %d", "%b %d", "%d.%m."):
        try:
            d = datetime.strptime(t, fmt).date().replace(year=today.year)
            return (d if d >= today else d.replace(year=today.year + 1)).isoformat()
        except ValueError:
            continue
    return None


def kg_text(kg: Decimal) -> str:
    """A weight as carriers should read it: exact to the hundredth, and never below the real weight (round 28: 116.9
    kg sent as 117 cost 0.33 EUR and 0.38 points; round 62: a rate for less than the shipment weighs is not a
    booking of it)."""
    t = f"{Decimal(kg).quantize(Decimal('0.01'), rounding=ROUND_CEILING):f}".rstrip("0").rstrip(".")
    return t or "0"


def is_confirmation(m: dict) -> bool:
    """An airline confirming a booking ('Booking BK-... confirmed', '... is confirmed'), not news after it."""
    return bool(re.match(r"^(?:re:\s*)?booking\s+\S+\s+confirmed", m.get("subject") or "", re.I)
                and not re.search(r"to quote we need", m.get("body") or "", re.I)) or \
        bool(re.search(r"\b(?:booking|reservation)\b[^.\n]*\b(?:is\s+)?confirmed\b", m.get("body") or "", re.I)
             and not re.search(r"to quote we need|delay|cancel", m.get("body") or "", re.I))


def booking_for(text: str) -> dict | None:
    """The booking a mail is about: one of our references (the airline's booking reference, our SM- reference,
    the rate id we booked with) appears in it."""
    for rec in store.records("booking"):
        b = rec["data"]
        if any(x and x in text for x in (b.get("rate_id"), b.get("team_reference"), b.get("booking_reference"))):
            return rec
    return None


def clean_reference(ref: str | None) -> str | None:
    """The carrier's reference as the id it is: "Please quote R-IR61CclGsFVVd1un when booking." came back from the
    reader as "R-IR61CclGsFVVd1un when booking.", which the portal would refuse as a rate id. Only a reference with
    words around it is cut to its id; one without spaces is kept as written, whatever its format."""
    if not ref or " " not in ref.strip():
        return ref.strip() if ref else ref
    m = re.search(r"\b[A-Za-z]{1,5}-[A-Za-z0-9_-]{3,}", ref)
    return m.group(0) if m else ref.strip()


def booked_air(b: dict) -> tuple[Decimal, Decimal] | None:
    """The flight price we booked and the rest of the booking's all-in total (an airline's mail prices the flight
    only; the rest is the pickup, and insurance or charges the customer asked to include: round 92 told a customer
    3301.88 instead of 3569.18 because the rest was taken as the pickup alone)."""
    try:
        if b.get("others") is not None:
            others = Decimal(str(b["others"]))
        else:
            others = Decimal(str((b.get("pickup") or {}).get("total") or 0))
        return Decimal(str(b.get("amount", "")).split()[0]) - others, others
    except Exception:
        return None


def confirmation_matches(b: dict, text: str) -> bool:
    """The airline confirms what we booked: our booking reference and the air price we booked at are both in its
    mail. Anything else (another price, no reference, a booking we made by mail) is news the agent should read."""
    booked = booked_air(b)
    return booked is not None and bool(b.get("booking_reference")) and b["booking_reference"] in text and \
        b.get("via") == "portal" and booked[0] in amounts_in(text)


def price_in_airline_mail(b: dict, body: str, confirmation: bool) -> tuple[dict, str, bool]:
    """What an airline's mail about our booking says about the price, worked out by code for the agent: the flight
    price we booked, or another one (a confirmation is the airline's word on what it charges: the all-in total
    follows it, as at booking). Returns the booking, the facts for the agent, and whether the price changed."""
    booked = booked_air(b)
    if booked is None:
        return b, "", False
    air, pickup = booked
    with_pickup = f" (with the rest of the all-in: pickup, insurance, charges, {pricing.fmt(pickup)})" if pickup else ""
    if air in amounts_in(body):
        return b, (f"Their price, {pricing.fmt(air)}, is the flight price we booked: the customer's all-in total "
                   f"stays {b['amount']}{with_pickup}."), False
    stated = {a for tok in re.findall(r"(\d[\d.,']*\d|\d)\s*(?:EUR|€)", body) for a in amounts_in(tok)}
    if confirmation and len(stated) == 1:
        new_air = stated.pop()
        quoted = b.get("quoted_amount") or b["amount"]
        now = pricing.fmt(new_air + pickup)
        return ({**b, "amount": now, "quoted_amount": quoted, "price_changed": {"quoted": quoted, "booked": now}},
                f"Their price for the flight is {pricing.fmt(new_air)}, not the {pricing.fmt(air)} we booked: the "
                f"all-in total is now {now}{with_pickup}, against the {quoted} we quoted (price_changed).", True)
    return b, f"What we booked: the flight at {pricing.fmt(air)}, all-in {b['amount']}{with_pickup}.", False


LANES_FRESH = 2 * 3600  # what a carrier told us about its lanes holds this long; then it is asked again


def lanes_told(email: str) -> dict | None:
    """The lanes a carrier told us it flies (its own 'We fly ...'), if it told us lately. 5U changes the setup
    about once an hour, so this knowledge expires and the carrier is asked again."""
    raw = store.kv_get(f"lanes:{email}")
    if not raw:
        return None
    told = json.loads(raw)
    return told if time.time() - told.get("at", 0) < LANES_FRESH else None


def amounts_in(text: str) -> set[Decimal]:
    """Every amount a mail writes, read the ways it can be written: 1,234.50 / 1.234,50 / 94.08 / 3,71 / 9408."""
    out: set[Decimal] = set()
    text = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))", "", text or "")  # 1 234,50 -> 1234,50
    for tok in re.findall(r"\d[\d.,']*\d|\d", text):
        t = tok.replace("'", "")
        if re.fullmatch(r"\d{1,3}(,\d{3})*(\.\d+)?|\d+(\.\d+)?", t):  # 1,234.50  94.08
            out.add(Decimal(t.replace(",", "")))
        if re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?", t):  # 1.234,50  3,71
            out.add(Decimal(t.replace(".", "").replace(",", ".")))
    # said rather than written (a transcribed voice message): "340 euros and 60 cents"
    for whole, cents in re.findall(r"(\d[\d,.']*)\s*(?:euros?|eur|dollars?|usd)\s*(?:and\s*)?(\d{1,2})\s*(?:cents?|ct)\b",
                                   text, re.I):
        for w in amounts_in(whole):
            out.add(w + Decimal(cents) / 100)
    return out


def read_in_mail(x: dict, body: str) -> bool:
    """The amount a reader took from a carrier mail is one the mail wrote (Sat 18:27: '94.08 EUR' read as 9408).
    Code owns the numbers: a small model's misplaced decimal must not become a price."""
    value = x.get("total") if x.get("total") is not None else x.get("rate_per_kg")
    if not x.get("available") or value is None:
        return True
    try:
        return Decimal(str(value)) in amounts_in(body)
    except Exception:
        return False


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
