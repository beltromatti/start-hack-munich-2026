"""The shared view must preserve human work and report failed input rather than pretending it succeeded."""
import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from app import browser, main


@pytest.mark.parametrize("url", ["http://start-hack.5u.ai/portal/ui", "https://5u.ai.evil.example/", "file:///etc/passwd"])
def test_sidecar_rejects_non_5u_urls_before_starting_chrome(monkeypatch, url):
    launch = AsyncMock()
    monkeypatch.setattr(browser, "browser", launch)
    with pytest.raises(HTTPException) as error:
        asyncio.run(browser.open_page("deal-1", {"url": url}))
    assert error.value.status_code == 400
    launch.assert_not_awaited()


def test_reconnecting_view_preserves_redirected_page_and_unfinished_form(monkeypatch):
    p = Mock(url="https://start-hack.5u.ai/portal/result")
    p.is_closed.return_value = False
    p.goto = AsyncMock()
    ctx = Mock(new_page=AsyncMock())
    monkeypatch.setitem(browser.state, "pages", {"deal-1": p})
    monkeypatch.setattr(browser, "browser", AsyncMock(return_value=ctx))
    monkeypatch.setattr(browser, "view", AsyncMock(return_value={"text": "unfinished form"}))
    assert asyncio.run(browser.open_page("deal-1", {}))["text"] == "unfinished form"
    p.goto.assert_not_awaited()
    ctx.new_page.assert_not_awaited()
    asyncio.run(browser.open_page("deal-1", {"reload": True}))
    p.goto.assert_awaited_once_with(browser.PORTAL, wait_until="domcontentloaded")


def test_two_deals_share_one_browser_start(monkeypatch):
    b = Mock(contexts=[object()])
    b.is_connected.return_value = True
    pw = Mock()
    pw.chromium.connect_over_cdp = AsyncMock(return_value=b)
    monkeypatch.setattr(browser, "state", {"pw": pw, "ctx": None, "browser": None, "pages": {}})
    monkeypatch.setattr(browser, "start_lock", asyncio.Lock())
    monkeypatch.setattr(browser, "chrome_endpoint", AsyncMock(return_value="http://127.0.0.1:9223"))
    async def connect():
        return await asyncio.gather(browser.browser(), browser.browser())
    contexts = asyncio.run(connect())
    assert contexts[0] is contexts[1]
    pw.chromium.connect_over_cdp.assert_awaited_once()


def test_persons_key_is_not_returned_to_agent(monkeypatch):
    p = Mock(url=browser.PORTAL)
    p.evaluate = AsyncMock(return_value=[{"i": 0, "label": "Team key", "type": "text", "value": "private-test-key"},
                                        {"i": 1, "label": "Origin", "type": "text", "value": "FRA"}])
    p.inner_text = AsyncMock(return_value="Result for private-test-key: 200 EUR")
    monkeypatch.setitem(browser.state, "pages", {"deal-1": p})
    result = asyncio.run(browser.view(p))
    assert "private-test-key" not in str(result)
    assert result["form"][1]["value"] == "FRA"


def test_input_proxy_propagates_missing_page_and_does_not_forward_arbitrary_url(monkeypatch):
    monkeypatch.setattr(main.store, "get", lambda _: {"type": "deal"})
    send = Mock(return_value=httpx.Response(404, text="no page open"))
    monkeypatch.setattr(httpx, "post", send)
    with pytest.raises(HTTPException) as error:
        main.portal_input("deal-1", "click", {"x": 4, "y": 9})
    assert error.value.status_code == 404
    send.return_value = httpx.Response(200, json={"url": browser.PORTAL, "text": "private page"})
    assert main.portal_input("deal-1", "open", {"url": "https://evil.example"}) == {"ok": True}
    assert send.call_args.kwargs["json"] == {"reload": False}
