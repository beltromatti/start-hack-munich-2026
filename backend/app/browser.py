"""A browser the agent and a person share, for 5U's portal page (the one place its rates live when the rate API
answers 503, behind a check meant for people).

One page per deal, in the installed desktop Chrome with a dedicated persistent profile. The agent reads and fills it through the `browser`
tool (by the labels a person sees, so the page may change its field names every load); the person sees it live in
the deal's conversation in our UI and does what only a person may do there: the check, the team key, a banner if
the agent cannot. Runs beside production, so a browser problem never stops the forwarder:

    cd backend && uv run python -m app.browser        (listens on 127.0.0.1:8010)
"""
import asyncio
import os
import shutil
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from playwright.async_api import async_playwright

PORT = 8010
PROFILE = Path(os.environ.get("PORTAL_BROWSER_PROFILE", Path(__file__).resolve().parents[1] / "data" / "portal-chrome"))
PORTAL = "https://start-hack.5u.ai/portal/ui"
state: dict = {"pw": None, "ctx": None, "browser": None, "pages": {}}
start_lock = asyncio.Lock()
SIZE = {"width": 720, "height": 860}


@asynccontextmanager
async def lifespan(_):
    yield
    if state["pw"]:
        # Disconnect only: Chrome and its cookies survive a sidecar restart.
        await state["pw"].stop()
    state.update(pw=None, ctx=None, browser=None, pages={})


app = FastAPI(lifespan=lifespan)


def chrome_command(port: int) -> list[str]:
    executable = os.environ.get("PORTAL_CHROME_PATH") or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" if sys.platform == "darwin"
        else shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser"))
    if not executable or not Path(executable).is_file():
        raise HTTPException(503, "Install Google Chrome or set PORTAL_CHROME_PATH")
    # Start Chrome itself, not Playwright's automation launcher. No headless mode, automation switches,
    # fingerprint patches or emulated device. CDP only connects the person's shared view and input.
    return [executable, f"--user-data-dir={PROFILE.resolve()}", f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check",
            f"--window-size={SIZE['width']},{SIZE['height'] + 100}", "about:blank"]


async def chrome_endpoint() -> str:
    PROFILE.mkdir(parents=True, exist_ok=True, mode=0o700)
    port_file = PROFILE / "shared-browser-port"
    async with httpx.AsyncClient(timeout=0.5, trust_env=False) as client:
        async def ready(port):
            try:
                r = await client.get(f"http://127.0.0.1:{port}/json/version")
                return r.status_code == 200 and bool(r.json().get("webSocketDebuggerUrl"))
            except (httpx.HTTPError, ValueError):
                return False
        if port_file.exists():
            try:
                port = int(port_file.read_text())
                if await ready(port):
                    return f"http://127.0.0.1:{port}"
            except ValueError:
                pass
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]  # A nonzero port; port 0 opts Chrome into automation mode.
        with (PROFILE / "chrome.log").open("ab") as log:
            process = subprocess.Popen(chrome_command(port), stdout=log, stderr=log, start_new_session=True)
        for _ in range(60):
            if await ready(port):
                port_file.write_text(str(port))
                return f"http://127.0.0.1:{port}"
            if process.poll() is not None:
                break
            await asyncio.sleep(0.2)
        raise HTTPException(503, "Desktop Chrome could not start; check portal-chrome/chrome.log and the desktop session")

FORM_JS = """() => [...document.querySelectorAll('input, select, textarea, button')]
  .filter(e => e.offsetParent !== null)
  .map((e, i) => { const t = e.tagName.toLowerCase();
     const l = (e.labels && e.labels[0] && e.labels[0].innerText)
       || (e.closest('label') && e.closest('label').innerText)
       || (t !== 'button' && e.previousElementSibling && e.previousElementSibling.innerText)
       || e.getAttribute('aria-label') || e.placeholder || (t === 'button' ? e.innerText : '') || '';
     return {i, tag: t, type: e.type || '', label: l.trim().slice(0, 80), value: t === 'button' ? '' : (e.value || '')}; })"""

FILL_JS = """([i, v]) => { const els = [...document.querySelectorAll('input, select, textarea, button')]
  .filter(e => e.offsetParent !== null); const e = els[i]; if (!e) return false;
  const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, v);
  e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); return true; }"""

CLICK_JS = """(i) => { const els = [...document.querySelectorAll('input, select, textarea, button')]
  .filter(e => e.offsetParent !== null); const e = els[i]; if (!e) return false; e.click(); return true; }"""


async def browser():
    async with start_lock:
        if state["browser"] is None or not state["browser"].is_connected():
            if state["pw"] is None:
                state["pw"] = await async_playwright().start()
            endpoint = await chrome_endpoint()
            b = await state["pw"].chromium.connect_over_cdp(endpoint, no_defaults=True)
            state.update(browser=b, ctx=b.contexts[0], pages={})
        return state["ctx"]


def page(deal: str):
    p = state["pages"].get(deal)
    if p is None or p.is_closed():
        raise HTTPException(404, "no page open for this deal")
    return p


async def view(p) -> dict:
    """What a person would see: the form's visible fields by label, and the page's visible text."""
    try:
        form = await p.evaluate(FORM_JS)
        text = await p.inner_text("body")
        marked = next((state.get("key_field", {}).get(deal) for deal, current in state["pages"].items() if current is p), None)
        for field in form:
            if field.get("value") and (field["i"] == marked or field.get("type") == "password" or
                    any(word in field["label"].lower() for word in ("key", "password", "token", "secret"))):
                text = text.replace(field["value"], "{team_key}")
                field["value"] = "{team_key}"
    except Exception as e:
        return {"error": repr(e)[:200]}
    return {"url": p.url, "form": form, "text": text[:3000]}


@app.post("/pages/{deal}")
async def open_page(deal: str, body: dict) -> dict:
    target = body.get("url") or PORTAL
    parsed = urlparse(target)
    if parsed.scheme != "https" or not (parsed.hostname == "5u.ai" or (parsed.hostname or "").endswith(".5u.ai")):
        raise HTTPException(400, "the browser opens 5U's sites only (https, *.5u.ai)")
    ctx = await browser()
    old = state["pages"].get(deal)
    if old and not old.is_closed():
        if not body.get("reload") and ("url" not in body or old.url == target):
            return await view(old)  # UI remounts must not reset a person's challenge or unfinished form.
        state.get("key_field", {}).pop(deal, None)
        await old.goto(target, wait_until="domcontentloaded")
        return await view(old)
    p = await ctx.new_page()
    state["pages"][deal] = p
    await p.goto(target, wait_until="domcontentloaded")
    return await view(p)


@app.get("/pages/{deal}")
async def read_page(deal: str) -> dict:
    return await view(page(deal))


@app.post("/pages/{deal}/fill")
async def fill(deal: str, body: dict) -> dict:
    """Fill fields by index (from the form view). Secrets are typed by the person, never here."""
    p = page(deal)
    form = await p.evaluate(FORM_JS)
    done, refused = [], []
    for i, v in body.get("fields", {}).items():
        f = next((x for x in form if str(x["i"]) == str(i)), None)
        if f is None or f["tag"] == "button":
            refused.append({"i": i, "why": "no such field"})
            continue
        if str(v).strip() == "{team_key}":  # the agent says where the key goes; the person's click types it
            state.setdefault("key_field", {})[deal] = int(i)
            done.append(f"{f['label']} (the person's key, on their click)")
            continue
        if any(w in f["label"].lower() for w in ("key", "password", "token", "secret")) or f["type"] == "password":
            refused.append({"i": i, "why": "a key or password: pass {team_key}, the person types it"})
            continue
        await p.evaluate(FILL_JS, [int(i), str(v)])
        done.append(f["label"])
    out = await view(p)
    return {**out, "filled": done, "refused": refused}


@app.post("/pages/{deal}/press")
async def press(deal: str, body: dict) -> dict:
    """Click a visible button by index (a banner's choice, a popup's close)."""
    p = page(deal)
    await p.evaluate(CLICK_JS, int(body["i"]))
    await asyncio.sleep(0.4)
    return await view(p)


@app.get("/pages/{deal}/shot")
async def shot(deal: str) -> Response:
    return Response(await page(deal).screenshot(type="jpeg", quality=70, scale="css"), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.post("/pages/{deal}/click")
async def click(deal: str, body: dict) -> dict:
    """The person clicks in the live view (x, y in the page's own pixels)."""
    await page(deal).mouse.click(float(body["x"]), float(body["y"]))
    return {"ok": True}


@app.post("/pages/{deal}/scroll")
async def scroll(deal: str, body: dict) -> dict:
    await page(deal).mouse.wheel(float(body.get("x", 0)), float(body.get("y", 0)))
    return {"ok": True}


@app.post("/pages/{deal}/focus")
async def focus(deal: str, body: dict) -> dict:
    await page(deal).bring_to_front()
    return {"ok": True}


@app.post("/pages/{deal}/type")
async def type_(deal: str, body: dict) -> dict:
    """The person types in the live view (into the field they clicked); key: Enter, Tab, Backspace."""
    p = page(deal)
    if body.get("into") == "key":  # the person's own key, on their click, into the field the agent marked
        idx = state.get("key_field", {}).get(deal)
        if idx is None:
            form = await p.evaluate(FORM_JS)
            f = next((x for x in form if x["tag"] == "input" and "key" in x["label"].lower()), None)
            idx = f["i"] if f else None
        if idx is None:
            return {"error": "no key field marked on the page: click the field, then paste the key below"}
        await p.evaluate(FILL_JS, [idx, str(body.get("text") or "")])
        return {"ok": True}
    if body.get("key"):
        await p.keyboard.press(body["key"])
    if body.get("text"):
        await p.keyboard.insert_text(str(body["text"]))
    return {"ok": True}


@app.delete("/pages/{deal}")
async def close(deal: str) -> dict:
    p = state["pages"].pop(deal, None)
    if p and not p.is_closed():
        await p.close()
    return {"ok": True}


@app.get("/size")
def size() -> dict:
    return SIZE


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
