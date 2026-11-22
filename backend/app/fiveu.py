"""The 5U API: mailbox, rate portal, bookings, board. One client, transient errors retried here.

Rules the code enforces, whatever a model or a mail says:
- the portal's per-minute rate limit is respected (we wait for the next window instead of failing);
- outbound mail is capped per recipient and per minute, so nobody gets spammed.
"""
import threading
import re
import time
from collections import defaultdict, deque
from typing import Any

import httpx

from . import store
from .config import settings


class FiveU:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.http = httpx.Client(base_url=base_url or settings.fiveu_base_url,
                                 headers={"X-API-Key": api_key or settings.fiveu_api_key}, timeout=20)
        self._rate_lock = threading.Lock()
        self._rate_left: int | None = None
        self._rate_reset = 0.0
        self._sent: dict[str, deque] = defaultdict(deque)
        self._last_poll = time.time()  # after a restart the old process may have just polled: wait one gap
        self._send_lock = threading.Lock()

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        for attempt in range(4):
            try:
                r = self.http.request(method, path, **kw)
            except httpx.TransportError as e:
                if attempt == 3:
                    raise
                store.log("fiveu", "error", f"{method} {path}: {e!r}, retrying")
                time.sleep(0.5 * 2 ** attempt)
                continue
            if r.status_code in (500, 502, 504) and attempt < 3:
                time.sleep(0.5 * 2 ** attempt)
                continue
            return r
        raise RuntimeError("unreachable")

    # ---- mailbox -------------------------------------------------------------------------------------------

    poll_gap = 5.5      # seconds between mailbox polls: 5U's limit ("one poll per 5 seconds", Sat 20:30) plus 10 % for
    #                     network jitter (a 5.0 s gap still drew a 429 at 20:40), raised by a 429
    _last_poll = 0.0

    def poll(self, since_id: int) -> tuple[list[dict], int]:
        """New mail since since_id. Keeps to 5U's poll limit: never polls sooner than it allows, and a 429 is a
        'not yet' (it sets the gap from 5U's own words and waits) and an alert, never a crash."""
        if time.time() - self._last_poll < self.poll_gap:
            return [], since_id
        self._last_poll = time.time()
        # one request, never retried here: a retry sooner than the limit is a second poll (a 429 of our own making);
        # a failed poll is simply the next tick's poll, one gap later
        try:
            r = self.http.request("GET", "/v1/mailbox/messages", params={"since_id": since_id, "limit": 200})
        except httpx.TransportError as e:
            store.log("router", "error", f"mailbox poll failed: {e!r}, polling again in {self.poll_gap:g}s")
            return [], since_id
        if r.status_code >= 500:
            store.log("router", "error", f"mailbox {r.status_code}, polling again in {self.poll_gap:g}s")
            return [], since_id
        if r.status_code == 429:
            try:
                d = r.json()
            except Exception:
                d = {}
            m = re.search(r"per\s+(\d+(?:\.\d+)?)\s*second", str(d.get("detail", "")))
            self.poll_gap = max(self.poll_gap, (float(m.group(1)) if m else 5.0) * 1.1)
            self._last_poll = time.time()  # the next poll waits a full gap from now
            # we keep to the limit, so a 429 means someone else polls with our team key, or 5U tightened it:
            # an error, so the team hears of it (it costs us time on every reply)
            store.log("router", "error", f"mailbox 429 '{d.get('detail', '')}': another client polling with our key, "
                      f"or a new limit; polling every {self.poll_gap:g}s")
            return [], since_id
        r.raise_for_status()
        d = r.json()
        return d["messages"], d["next_since_id"]

    def send(self, to: str, subject: str, body: str, in_reply_to: int | None = None) -> dict:
        with self._send_lock:
            now = time.time()
            q = self._sent[to]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= 6:
                raise RuntimeError(f"outbound limit: {to} already got 6 mails this minute")
            q.append(now)
        payload: dict[str, Any] = {"to": to, "subject": subject, "body": body}
        if in_reply_to is not None:
            payload["in_reply_to"] = in_reply_to
        r = self._req("POST", "/v1/mailbox/messages", json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"send to {to} failed: {r.status_code} {r.text[:300]}")
        return r.json()

    def attachment(self, mail_id: int, attachment_id: Any) -> bytes:
        r = self._req("GET", f"/v1/mailbox/messages/{mail_id}/attachments/{attachment_id}")
        r.raise_for_status()
        return r.content

    # ---- portal --------------------------------------------------------------------------------------------

    def ports(self) -> list[dict]:
        r = self._req("GET", "/v1/portal/ports")
        r.raise_for_status()
        return r.json()["lanes"]

    def brackets(self, airline: str) -> list[int] | None:
        r = self._req("GET", "/v1/portal/brackets", params={"airline": airline})
        return r.json()["breaks_kg"] if r.status_code == 200 else None

    def rate(self, origin: str, destination: str, airline: str, weight_kg: Any, volume_cbm: Any = None) -> dict:
        """One priced rate, or {"error", "status", "detail"}. Waits for the next window when the limit is used up."""
        params = {"origin": origin, "destination": destination, "airline": airline, "weight_kg": str(weight_kg)}
        if volume_cbm:
            params["volume_cbm"] = str(volume_cbm)
        with self._rate_lock:
            for _ in range(3):
                if self._rate_left == 0 and time.time() < self._rate_reset:
                    time.sleep(self._rate_reset - time.time())
                r = self._req("GET", "/v1/portal/rates", params=params)
                left = r.headers.get("X-RateLimit-Remaining")
                self._rate_left = int(left) if left is not None and left.isdigit() else None
                if self._rate_left == 0:
                    self._rate_reset = time.time() + 60
                if r.status_code == 429:
                    wait = float(r.headers.get("Retry-After") or 5)
                    store.log("fiveu", "info", f"portal rate limit, waiting {wait:.0f}s")
                    self._rate_left, self._rate_reset = 0, time.time() + wait
                    continue
                if r.status_code == 200:
                    return r.json()
                return {"error": True, "status": r.status_code, "detail": _detail(r)}
        return {"error": True, "status": 429, "detail": "rate limit"}

    def rate_from_page(self, origin: str, destination: str, airline: str, weight_kg: Any,
                       volume_cbm: Any = None) -> dict:
        """One priced rate from the portal's web page, for when the rate API fails. 5U: "Rates are still published on
        the portal page" (round 93); rounds 95-100 the lane's fastest airline was missing and the winners booked it.
        Same shape as rate() (its rate_id books through the API), or {"error", "status", "detail"}."""
        form = {"team_key": self.http.headers.get("X-API-Key", ""), "origin": origin, "destination": destination,
                "airline": airline, "weight_kg": str(weight_kg), "volume_cbm": str(volume_cbm or "")}
        try:
            r = httpx.post(portal_page_url(str(self.http.base_url)), data=form, timeout=20, follow_redirects=True)
        except httpx.TransportError as e:
            return {"error": True, "status": 0, "detail": f"portal page: {e!r}"}
        rate = read_rate_page(r.text)
        if rate is None:
            return {"error": True, "status": r.status_code, "detail": "portal page: no rate in the answer"}
        return rate

    def book(self, rate_id: str, team_reference: str) -> tuple[int, dict]:
        r = self._req("POST", "/v1/portal/bookings", json={"rate_id": rate_id, "team_reference": team_reference})
        try:
            body = r.json()
        except ValueError:
            body = {"detail": r.text[:300]}
        return r.status_code, body

    def board(self) -> dict:
        """The public leaderboard: every team's rank, totals, accepted, bookings, the last rounds."""
        r = self._req("GET", "/v1/board")
        r.raise_for_status()
        return r.json()

    def board_me(self) -> dict:
        r = self._req("GET", "/v1/board/me")
        r.raise_for_status()
        return r.json()


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json()
        return str(d.get("detail") or d)
    except ValueError:
        return r.text[:300]


def portal_page_url(api_base: str) -> str:
    """The portal page lives on the site, the API on api.: https://api.start-hack.5u.ai -> .../portal/ui."""
    return re.sub(r"//api\.", "//", api_base.rstrip("/")) + "/portal/ui"


def read_rate_page(html: str) -> dict | None:
    """The rate table of the portal page (cells by id: rate_id, airline, chargeable_weight_kg, total, currency,
    transit_days, valid_until) in the shape of the API's rate. Digits hidden with display:none are dropped (the page
    did that on Sun 00:52)."""
    hidden = set(re.findall(r"\.([\w-]+)\s*\{[^}]*display\s*:\s*none", html))
    for cls in hidden:
        html = re.sub(rf'<span[^>]*class="[^"]*\b{re.escape(cls)}\b[^"]*"[^>]*>.*?</span>', "", html, flags=re.S)
    cells = {k: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", v)).strip()
             for k, v in re.findall(r'<td[^>]*\bid="(\w+)"[^>]*>(.*?)</td>', html, re.S)}
    num = {k: cells.get(k, "").replace(" ", "") for k in ("total", "chargeable_weight_kg", "transit_days")}
    if not cells.get("rate_id") or not num["total"]:
        return None
    m = re.match(r"(.*?)\s*\(([A-Z0-9]{2})\)$", cells.get("airline", ""))
    try:
        return {"rate_id": cells["rate_id"], "airline": m.group(1) if m else cells.get("airline", ""),
                "airline_code": m.group(2) if m else None,
                "chargeable_weight_kg": num["chargeable_weight_kg"] or None, "total": num["total"],
                "currency": cells.get("currency") or "EUR", "transit_days": int(float(num["transit_days"])),
                "valid_until": cells.get("valid_until"), "source": "page"}
    except (KeyError, ValueError):
        return None
