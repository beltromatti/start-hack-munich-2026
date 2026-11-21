"""Build the expected answer for every synthetic mail and drop the mails into FakeMail's inbox.

    cd backend && uv run python -m synthetic.build          # offline, uses portal_cache.json
    cd backend && uv run python -m synthetic.build --live   # also fetches missing portal prices (6.5 s per call)

Writes backend/synthetic/expected.json (committed: the answer key) and backend/data/inbox/<id>.json (gitignored:
what FakeMail reads). The pipeline must never read expected.json.

Reference pricing, as the rate sheets state it (tariffs.json `rules`): chargeable = max(kg, cbm x 167), rate by the
highest break at or below the billed weight, minimum on freight before surcharges, fuel and security per billed kg.
Billed weight is the chargeable weight or any higher break, whichever is cheapest (299 kg billed as 300 kg).
"""
import csv
import json
import sys
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import httpx

from synthetic.mails import MAILS, US

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KIT = ROOT / "docs" / "challenges" / "5u-kit"
CACHE = HERE / "portal_cache.json"
CBM_KG = Decimal(167)
CENT = Decimal("0.01")


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def chargeable(kg: Decimal, cbm: Decimal | None) -> Decimal:
    return max(kg, (cbm or Decimal(0)) * CBM_KG)


def sheet_price(lane: dict, cw: Decimal) -> dict:
    """Cheapest total for one rate-sheet lane: bill at cw or at any higher break."""
    breaks = [Decimal(b) for b in lane["breaks_kg"]]
    rates = [Decimal(r) for r in lane["rates_eur_per_kg"]]
    surcharge = Decimal(lane["fuel_eur_per_kg"]) + Decimal(lane["security_eur_per_kg"])
    best = None
    for billed in [cw] + [b for b in breaks if b > cw]:
        rate = rates[max(i for i, b in enumerate(breaks) if b <= billed)]
        freight = max(Decimal(lane["minimum_eur"]), rate * billed)
        total = money(freight + surcharge * billed)
        if best is None or total < best["total_eur"]:
            best = dict(billed_kg=billed, rate_eur_per_kg=rate, total_eur=total)
    return best


def load_kit():
    tariffs = json.loads((KIT / "tariffs.json").read_text())
    with open(KIT / "start-kit" / "carrier-list.csv") as f:
        carriers = list(csv.DictReader(f))
    with open(KIT / "start-kit" / "pickup_zones.csv") as f:
        zones = {r["zone"]: r for r in csv.DictReader(f)}
    return tariffs, carriers, zones


class Portal:
    """Cached /v1/portal calls. Offline it only reads the cache, live it fills the gaps at 6.5 s per call."""

    def __init__(self, live: bool):
        self.live = live
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        self.http = None
        if live:
            env = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line)
            self.http = httpx.Client(base_url=env["FIVEU_BASE_URL"], timeout=30,
                                     headers={"X-API-Key": env["FIVEU_API_KEY"]})

    def get(self, path: str, **params):
        key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        if key not in self.cache and self.live:
            time.sleep(6.5)
            r = self.http.get(path, params=params)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "60")))
                r = self.http.get(path, params=params)
            self.cache[key] = dict(status=r.status_code, body=r.json(), fetched_at=time.strftime("%Y-%m-%d %H:%M"))
            CACHE.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
            print("portal", r.status_code, key, file=sys.stderr)
        return self.cache.get(key)


def portal_offers(portal: Portal, origin: str, dest: str, kg: Decimal, cbm: Decimal | None) -> list[dict]:
    ports = portal.get("/v1/portal/ports")
    if not ports:
        return []
    lane = next((l for l in ports["body"]["lanes"] if l["origin"] == origin and l["destination"] == dest), None)
    offers = []
    for a in (lane or {}).get("airlines", []):
        br = portal.get("/v1/portal/brackets", airline=a["code"])
        cw = chargeable(kg, cbm)
        tries = [dict(weight_kg=str(kg), volume_cbm=str(cbm))] if cbm else [dict(weight_kg=str(kg))]
        if br and br["status"] == 200:
            higher = [b for b in br["body"]["breaks_kg"] if Decimal(b) > cw]
            if higher:
                tries.append(dict(weight_kg=str(higher[0])))
        best = None
        for t in tries:
            r = portal.get("/v1/portal/rates", origin=origin, destination=dest, airline=a["code"], **t)
            if not r or r["status"] != 200:
                continue
            b = r["body"]
            total = Decimal(b["total"])
            if b.get("currency") == "USD":
                total = money(total * Decimal(b["fx_eur_per_usd"]))
            o = dict(source="portal", airline=b["airline"], airline_code=b["airline_code"],
                     billed_kg=Decimal(b["chargeable_weight_kg"]), total_eur=total,
                     transit_days=b.get("transit_days"), portal_total=b["total"], portal_currency=b.get("currency"),
                     asked=t)
            if best is None or o["total_eur"] < best["total_eur"]:
                best = o
        if best:
            offers.append(best)
    return offers


def expect_rfq(case: dict, tariffs, carriers, zones, portal: Portal) -> dict:
    exp = dict(case)
    if case.get("pickup_postcode"):
        zone = zones.get(case["pickup_postcode"][:2])
        exp["pickup_zone"] = zone["zone"] if zone else None
        exp["pickup_airport"] = zone["airport"] if zone else None
        exp["truckers_to_ask"] = sorted(c["email"] for c in carriers
                                        if c["kind"] == "trucker" and exp["pickup_zone"] in c["serves"].split())
    if case.get("action") == "email_airline":
        exp["airlines_to_email"] = sorted(c["email"] for c in carriers
                                          if c["kind"] == "airline" and case["destination"] in c["serves"].split())
    if case.get("action") != "quote":
        return exp
    kg = Decimal(case["actual_kg"])
    cbm = Decimal(case["volume_cbm"]) if case.get("volume_cbm") else None
    cw = chargeable(kg, cbm)
    exp["chargeable_kg"] = str(cw)
    offers = []
    for lane in tariffs["lanes"]:
        if lane["origin"] == case["origin"] and lane["destination"] == case["destination"]:
            p = sheet_price(lane, cw)
            offers.append(dict(source="sheet", airline=lane["airline"], transit_days=lane["transit_days"], **p))
    offers += portal_offers(portal, case["origin"], case["destination"], kg, cbm)
    offers.sort(key=lambda o: o["total_eur"])
    exp["offers"] = [{k: str(v) if isinstance(v, Decimal) else v for k, v in o.items()} for o in offers]
    if offers:
        fastest = min(offers, key=lambda o: (o["transit_days"] if o["transit_days"] is not None else 99, o["total_eur"]))
        pick = offers[0] if case["preference"] != "fastest" else fastest
        exp["expected_quote"] = dict(airline=pick["airline"], source=pick["source"], total_eur=str(pick["total_eur"]),
                                     currency="EUR", transit_days=pick["transit_days"],
                                     note="airport to airport; add the cheapest trucker bid" if case.get("pickup_postcode") else None)
    return exp


def main(live: bool = False) -> dict:
    tariffs, carriers, zones = load_kit()
    portal = Portal(live)
    inbox = ROOT / "backend" / "data" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    expected = {}
    t0 = 1_795_273_200  # Sat 21.11.2026 16:00 CET, the first real RFQ, then one mail every 6 min
    for n, m in enumerate(MAILS):
        mail = dict(id=m["id"], **{"from": m["frm"]}, to=US, subject=m["subject"], body=m["body"],
                    thread_id=m.get("thread"), received_at=t0 + 360 * n, attachments=m.get("attachments", []))
        (inbox / f"{m['id']}.json").write_text(json.dumps(mail, indent=2, ensure_ascii=False))
        case = m["case"]
        exp = expect_rfq(case, tariffs, carriers, zones, portal) if m["kind"] == "rfq" else dict(case)
        expected[m["id"]] = dict(kind=m["kind"], **exp)
    (HERE / "expected.json").write_text(json.dumps(expected, indent=1, ensure_ascii=False))
    return expected


if __name__ == "__main__":
    out = main(live="--live" in sys.argv)
    for mid, e in out.items():
        q = e.get("expected_quote") or {}
        print(mid, e["kind"], e.get("action"), q.get("total_eur", ""), q.get("airline", ""), q.get("source", ""))
