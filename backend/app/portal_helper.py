"""The person's assistant for 5U's portal page, when the rate API answers 503 (Sun from 00:19).

5U's page shows those rates to people who pass its check. This helper runs beside production on the desk's Mac,
in a visible Chrome window: for each airline a request is missing it opens the page, fills what the person would
type from our record (origin, destination, weight, volume, airline: found by their visible labels), rings, and
waits. The person answers the cookie wall, enters the team key (or the browser fills it), passes the check and
sends. The helper then reads the result as shown on screen and adds it to the deal like a portal price; the agent
quotes as usual. It never touches the check or the key.

Run (operator mode on in the UI):  cd backend && uv run python -m app.portal_helper
"""
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import store
from .forwarder import OPERATOR_WAIT, _since, add_portal_page_rate, read_portal_page

PORTAL = "https://start-hack.5u.ai/portal/ui"
PROFILE = Path(__file__).resolve().parent.parent / "data" / "portal-profile"  # keeps cookies and autofill
FILL = {"origin": "origin", "destination": "destination", "weight": "weight", "volume": "volume", "airline": "airline"}

LABELS_JS = """() => [...document.querySelectorAll('input, select, textarea')].filter(e => e.offsetParent !== null)
  .map(e => { const l = (e.labels && e.labels[0] && e.labels[0].innerText)
       || (e.closest('label') && e.closest('label').innerText)
       || (e.previousElementSibling && e.previousElementSibling.innerText) || e.placeholder || '';
     return {name: e.getAttribute('name'), label: l.trim().toLowerCase()}; })"""


def ring() -> None:
    subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])


def needed() -> list[tuple[str, dict, dict]]:
    """(deal_id, request, airline) still missing, while operator mode is on and the deal is inside its window."""
    if store.kv_get("operator_on") != "1":
        return []
    out = []
    for r in store.records("deal"):
        pm = r["data"].get("portal_missing") or {}
        if r["status"] in ("new", "pricing") and pm.get("airlines") and (_since(r["data"].get("received_at")) or 999) < OPERATOR_WAIT:
            out += [(r["id"], r["data"]["request"], a) for a in pm["airlines"]]
    return out


def values(req: dict, a: dict) -> dict:
    kg = f"{float(req['weight_kg']):g}"
    return {"origin": req["origin"], "destination": req["destination"], "weight": kg,
            "volume": f"{float(req['volume_cbm']):g}" if req.get("volume_cbm") else "", "airline": a.get("code") or a["name"]}


def fill(page, v: dict) -> int:
    """Fill the fields a person would type, by their visible labels; returns how many were filled."""
    done = 0
    for f in page.evaluate(LABELS_JS):
        if not f["name"] or "key" in f["label"]:
            continue
        for word, k in FILL.items():
            if word in f["label"] and v.get(k):
                page.fill(f'[name="{f["name"]}"]', v[k])
                done += 1
                break
    return done


def serve() -> None:
    handled: set[tuple[str, str]] = set()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), channel="chrome", headless=False,
                                                   viewport={"width": 900, "height": 900})
        print("portal helper ready: waiting for missing portal prices (operator mode on)", flush=True)
        while True:
            for deal_id, req, a in needed():
                key = (deal_id, a["name"])
                if key in handled:
                    continue
                handled.add(key)
                v = values(req, a)
                page = ctx.new_page()
                page.goto(PORTAL)
                page.bring_to_front()
                ring()
                print(f"{deal_id}: {req['origin']}-{req['destination']} {v['weight']} kg {v['airline']}: fill and send",
                      flush=True)
                filled, read = 0, None
                end = time.time() + 120
                while time.time() < end and not page.is_closed():
                    if filled < 4:  # the form shows after the cookie wall: fill it as soon as it is there
                        try:
                            filled = max(filled, fill(page, v))
                        except Exception:
                            pass
                    try:
                        text = page.inner_text("body")
                    except Exception:
                        break
                    r = read_portal_page(text)
                    if r["rate_id"] and r["total"] and r["days"]:
                        read = r
                        break
                    time.sleep(0.5)
                if read:
                    out = add_portal_page_rate(deal_id, a["name"], read["total"], read["days"], read["rate_id"],
                                               None, "portal helper")
                    print(f"  added {a['name']}: {read['total']} EUR, {read['days']} d, {read['rate_id']} {out.get('error', '')}",
                          flush=True)
                    page.close()
                else:
                    print(f"  no result read for {a['name']}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    serve()
