"""Jan's answer key (origin/jan: backend/synthetic) against main's pricing.py and the forwarder's portal logic.

    cd backend && uv run python -m research.check_key <path to backend/synthetic>

Offline: portal prices come from portal_cache.json. Result Sat 21 Nov 15:25: 18 of 18 priced cases exact.
"""
import json, sys
from decimal import Decimal as D
from app import kit, pricing
from app.pricing import Offer

J = sys.argv[1]
exp = json.load(open(f"{J}/expected.json"))
cache = json.load(open(f"{J}/portal_cache.json"))
w = kit.load(None)
ports = cache["/v1/portal/ports?"]["body"]["lanes"]
w.portal = {(l["origin"], l["destination"]): l["airlines"] for l in ports}
for k, v in cache.items():
    if k.startswith("/v1/portal/brackets") and v["status"] == 200:
        w.brackets[v["body"]["airline_code"]] = v["body"]["breaks_kg"]

misses = []
def rate(o, d, code, wt, cbm):
    keys = [f"/v1/portal/rates?airline={code}&destination={d}&origin={o}&volume_cbm={cbm}&weight_kg={wt}",
            f"/v1/portal/rates?airline={code}&destination={d}&origin={o}&weight_kg={wt}"]
    for k in keys:
        if k in cache and cache[k]["status"] == 200:
            return cache[k]["body"]
    misses.append(keys[0]); return None

bad = 0
for mid, e in exp.items():
    if e.get("action") != "quote":
        continue
    o, d = e["origin"], e["destination"]
    kg = D(e["actual_kg"]); cbm = D(e["volume_cbm"]) if e.get("volume_cbm") else None
    cw = pricing.chargeable(kg, cbm)
    offers = []
    for lane in w.sheet(o, d):
        total, billed = pricing.sheet_price(lane, kg, cbm)
        offers.append(Offer("air", lane["airline"], total, D(lane["transit_days"]), "sheet", None, billed))
    skipped_nb = []
    for a in w.portal.get((o, d), []):
        weights = [kg]
        nb = pricing.next_break(w.brackets.get(a["code"], []), cw)
        if nb is not None and nb / cw < D("1.5"):
            weights.append(nb)
        elif nb is not None:
            skipped_nb.append((a["code"], nb))
        for wt in weights:
            r = rate(o, d, a["code"], wt, e.get("volume_cbm") if wt == kg else None)
            if r:
                offers.append(Offer("air", r["airline"], D(r["total"]), D(r["transit_days"]), "portal", r["rate_id"], D(r["chargeable_weight_kg"])))
    q = pricing.quote(offers, [], e["preference"], False)
    x = e["expected_quote"]
    ours, theirs = D(q["total"]), D(x["total_eur"])
    diff = (ours / theirs - 1) * 100
    flag = "OK " if ours == theirs and q["air"]["carrier"] == x["airline"] else ("!! " if abs(diff) > 5 else "~  ")
    if flag != "OK ": bad += 1
    print(f"{flag}{mid} {o}-{d} cw {cw} {e['preference']:9} ours {ours} {q['air']['carrier']} ({q['air']['source']},{q['transit_days']}d) | key {theirs} {x['airline']} ({x['source']},{x['transit_days']}d) | {diff:+.2f}% | skipped next-break {skipped_nb}")
    print("      offers:", ", ".join(f"{p.carrier.split()[0]} {p.total}/{p.days}d/{p.source}" for p in sorted(offers, key=lambda p: p.total)))
print("mismatches:", bad, "| cache misses:", misses)
