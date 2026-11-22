"""The agent's desktop browser, visible and interactive in the deal's conversation.

One page per deal, in the installed desktop Chrome with a dedicated persistent profile. The agent reads and fills it through the `browser`
tool by current labels or screenshots, including 5U's checks and the team key. Observers can watch without
being needed for progress. Runs beside production, so a browser problem never stops the forwarder:

    cd backend && uv run python -m app.browser        (listens on 127.0.0.1:8010)
"""
import asyncio
import base64
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
from .config import settings

PORT = 8010
PROFILE = Path(os.environ.get("PORTAL_BROWSER_PROFILE", Path(__file__).resolve().parents[1] / "data" / "portal-chrome"))
PORTAL = "https://start-hack.5u.ai/portal/ui"
state: dict = {"pw": None, "ctx": None, "browser": None, "pages": {}}
start_lock = asyncio.Lock()
SIZE = {"width": 720, "height": 860}


def allowed(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname == "5u.ai" or (parsed.hostname or "").endswith(".5u.ai"))


def safe_page(deal: str):
    p = page(deal)
    if not allowed(p.url):
        raise HTTPException(400, "the browser acts on 5U's sites only; reopen the portal")
    return p


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
     if (!e.hasAttribute('data-forwarder-field')) {
       window.__forwarderNextField = (window.__forwarderNextField || 0) + 1;
       e.setAttribute('data-forwarder-field', String(window.__forwarderNextField));
     }
     i = Number(e.getAttribute('data-forwarder-field'));
     const r = e.getBoundingClientRect();
     return {i, tag: t, type: e.type || '', label: l.trim().slice(0, 120), value: t === 'button' ? '' : (e.value || ''),
       disabled: e.disabled, options: t === 'select' ? [...e.options].map(o => ({value:o.value, label:o.label})) : undefined,
       box: {x:r.x, y:r.y, width:r.width, height:r.height}}; })"""

FILL_JS = """([i, v]) => { const e = document.querySelector('[data-forwarder-field="' + i + '"]'); if (!e) return false;
  const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, v);
  e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); return true; }"""

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


async def view(p, include_image: bool = False) -> dict:
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
    if settings.fiveu_api_key:
        text = text.replace(settings.fiveu_api_key, "{team_key}")
    visual = await p.evaluate("""() => [...document.querySelectorAll('canvas, img, iframe')]
        .filter(e => e.getBoundingClientRect().width > 30 && e.getBoundingClientRect().height > 20)
        .map(e => ({tag:e.tagName.toLowerCase(), label:e.getAttribute('alt') || e.title || '',
          box:{x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,
               width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}}))""")
    out = {"url": p.url, "form": form, "text": text[:6000], "visual_elements": visual,
           "hint": "look returns a screenshot when a check or control is not readable in text" if visual else None}
    if include_image or any(e.get("tag") in ("canvas", "iframe") for e in visual):
        # A drawn check must be seen before it expires; include it in this same observation, no extra model turn.
        sensitive = [p.locator(f'[data-forwarder-field="{f["i"]}"]') for f in form
                     if f.get("value") == "{team_key}" or f.get("type") == "password"]
        raw = await p.screenshot(type="jpeg", quality=80, scale="css", mask=sensitive)
        out["_image"] = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    return out


@app.post("/pages/{deal}")
async def open_page(deal: str, body: dict) -> dict:
    target = body.get("url") or PORTAL
    if not allowed(target):
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
    await p.bring_to_front()
    await p.goto(target, wait_until="domcontentloaded")
    return await view(p)


async def fill_fields(deal: str, fields: dict) -> dict:
    """Trusted browser input, resolving a credential alias only on the approved origin."""
    p = safe_page(deal)
    form = await p.evaluate(FORM_JS)
    done = []
    for i, value in fields.items():
        f = next((x for x in form if str(x["i"]) == str(i)), None)
        if not f or f["tag"] == "button":
            return {"error": f"no editable field {i}; read the current form", "filled": done}
        sensitive = f["type"] == "password" or any(w in f["label"].lower() for w in ("key", "password", "token", "secret"))
        value = str(value)
        if value == "{team_key}":
            if not sensitive:
                return {"error": "the team key can only fill a labelled key/password field", "filled": done}
            if not settings.fiveu_api_key:
                return {"error": "FIVEU_API_KEY is not configured", "filled": done}
            value = settings.fiveu_api_key
            state.setdefault("key_field", {})[deal] = int(i)
        elif sensitive:
            return {"error": "use {team_key} for the key; it is resolved by the backend", "filled": done}
        element = p.locator(f'[data-forwarder-field="{int(i)}"]')
        if f["tag"] == "select":
            choice = next((o["value"] for o in f.get("options", []) if o["value"] == value or o["label"] == value), value)
            await element.select_option(value=choice, timeout=2000)
        elif f["type"] in ("checkbox", "radio"):
            await element.set_checked(value.lower() in ("true", "1", "yes", "checked"), timeout=2000)
        else:
            await element.fill(value, timeout=2000)
        done.append(f["label"])
    return {"filled": done}


@app.post("/pages/{deal}/act")
async def act(deal: str, body: dict) -> dict:
    """One ordered batch; stop on the first failed action and return the actual page for recovery."""
    completed = []
    await safe_page(deal).bring_to_front()  # Native Chrome throttles background tabs; input needs a live render loop.
    for step in body.get("actions") or []:
        try:
            p = safe_page(deal)
            kind = step["kind"]
            if kind == "fill":
                result = await fill_fields(deal, {str(step["i"]): step.get("value") or ""})
                if result.get("error"):
                    return {**await view(p), **result, "completed": completed}
            elif kind == "click":
                if step.get("i") is not None:
                    # Assign stable references to any controls added since the last observation.
                    await p.evaluate(FORM_JS)
                    await p.locator(f'[data-forwarder-field="{int(step["i"])}"]').click(timeout=2000)
                else:
                    await p.mouse.click(float(step["x"]), float(step["y"]))
            elif kind == "press":
                await p.keyboard.press(step["value"])
            elif kind == "type":
                await p.keyboard.insert_text(step.get("value") or "")
            elif kind == "scroll":
                await p.mouse.wheel(float(step.get("x") or 0), float(step.get("y") or 0))
            elif kind == "wait":
                await asyncio.sleep(min(max(float(step.get("ms") or 0), 0), 3000) / 1000)
            elif kind == "reload":
                await p.reload(wait_until="domcontentloaded")
                state.get("key_field", {}).pop(deal, None)
            else:
                raise ValueError(f"unknown browser action {kind}")
            completed.append(kind)
        except Exception as exc:
            error = str(exc).replace(settings.fiveu_api_key, "{team_key}") if settings.fiveu_api_key else str(exc)
            return {**await view(page(deal)), "error": error[:400], "completed": completed}
    # Allow immediate DOM results and navigation to settle, not a fixed multi-second delay per field.
    await asyncio.sleep(0.15)
    return {**await view(page(deal)), "completed": completed}


@app.get("/pages/{deal}/look")
async def look(deal: str) -> dict:
    p = safe_page(deal)
    return await view(p, include_image=True)


@app.get("/pages/{deal}")
async def read_page(deal: str) -> dict:
    return await view(page(deal))


@app.post("/pages/{deal}/fill")
async def fill(deal: str, body: dict) -> dict:
    result = await fill_fields(deal, body.get("fields", {}))
    return {**await view(page(deal)), **result}


@app.post("/pages/{deal}/press")
async def press(deal: str, body: dict) -> dict:
    """Click a visible button by index (a banner's choice, a popup's close)."""
    return await act(deal, {"actions": [{"kind": "click", "i": int(body["i"])}]})


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
