"""The agent's browser for 5U's portal page (the one place its rates live when the rate API answers 503).

One page per deal, in a headless Chrome on the desk's Mac. The agent reads and fills it through the `browser`
tool (by the labels a person sees, so the page may change its field names every load); the team key is typed here
from the settings, never shown to the model. The team watches the page in the deal's conversation and never acts
on it: 5U, Sun 04:06, "If the harness asks a person to solve anything, that's a human". Runs beside production, so
a browser problem never stops the forwarder:

    cd backend && uv run python -m app.browser        (listens on 127.0.0.1:8010)
"""
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from playwright.async_api import async_playwright

from .config import settings

PORT = 8010
app = FastAPI()
state: dict = {"pw": None, "ctx": None, "pages": {}}
SIZE = {"width": 720, "height": 860}

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
    if state["ctx"] is None:
        state["pw"] = await async_playwright().start()
        b = await state["pw"].chromium.launch(channel="chrome", headless=True)
        state["ctx"] = await b.new_context(viewport=SIZE)
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
    except Exception as e:
        return {"error": repr(e)[:200]}
    return {"url": p.url, "form": form, "text": text[:3000]}


@app.post("/pages/{deal}")
async def open_page(deal: str, body: dict) -> dict:
    ctx = await browser()
    old = state["pages"].get(deal)
    if old and not old.is_closed():
        await old.close()
    p = await ctx.new_page()
    state["pages"][deal] = p
    await p.goto(body["url"], wait_until="domcontentloaded")
    await asyncio.sleep(1.0)
    return await view(p)


@app.get("/pages/{deal}")
async def read_page(deal: str) -> dict:
    return await view(page(deal))


@app.post("/pages/{deal}/fill")
async def fill(deal: str, body: dict) -> dict:
    """Fill fields by index (from the form view). The team key is typed here from the settings, never by a person."""
    p = page(deal)
    form = await p.evaluate(FORM_JS)
    done, refused = [], []
    for i, v in body.get("fields", {}).items():
        f = next((x for x in form if str(x["i"]) == str(i)), None)
        if f is None or f["tag"] == "button":
            refused.append({"i": i, "why": "no such field"})
            continue
        if str(v).strip() == "{team_key}":  # the agent says where the key goes; the system types it
            await p.evaluate(FILL_JS, [int(i), settings.fiveu_api_key])
            done.append(f"{f['label']} (the team key)")
            continue
        if any(w in f["label"].lower() for w in ("key", "password", "token", "secret")) or f["type"] == "password":
            refused.append({"i": i, "why": "a key or password: pass {team_key}, the system types it"})
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
    return Response(await page(deal).screenshot(type="jpeg", quality=70), media_type="image/jpeg")


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
