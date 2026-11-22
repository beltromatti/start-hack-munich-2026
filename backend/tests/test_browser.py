"""The shared view must preserve human work and report failed input rather than pretending it succeeded."""
import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from app import browser, main
from app import tools, store, kit, llm, agent
from app.fake5u import FakeFiveU
from app.forwarder import Forwarder, read_portal_page
from dataclasses import replace


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


def test_key_alias_is_filled_by_backend_and_never_on_an_unapproved_origin(monkeypatch):
    field = Mock(fill=AsyncMock())
    p = Mock(url=browser.PORTAL)
    p.is_closed.return_value = False
    p.locator.return_value = field
    p.evaluate = AsyncMock(return_value=[{"i": 3, "tag": "input", "type": "password", "label": "Team key"}])
    monkeypatch.setitem(browser.state, "pages", {"key-test": p})
    monkeypatch.setattr(browser, "settings", replace(browser.settings, fiveu_api_key="test-private-key"))
    result = asyncio.run(browser.fill_fields("key-test", {"3": "{team_key}"}))
    field.fill.assert_awaited_once_with("test-private-key", timeout=2000)
    assert "test-private-key" not in str(result)
    p.url = "https://outside.example/login"
    with pytest.raises(HTTPException):
        asyncio.run(browser.fill_fields("key-test", {"3": "{team_key}"}))
    assert field.fill.await_count == 1


def test_failed_fill_stops_batch_before_submit(monkeypatch):
    p = Mock(url=browser.PORTAL)
    p.is_closed.return_value = False
    p.bring_to_front = AsyncMock()
    p.mouse.click = AsyncMock()
    monkeypatch.setitem(browser.state, "pages", {"batch-test": p})
    monkeypatch.setattr(browser, "fill_fields", AsyncMock(return_value={"error": "field changed"}))
    monkeypatch.setattr(browser, "view", AsyncMock(return_value={"text": "new form"}))
    out = asyncio.run(browser.act("batch-test", {"actions": [
        {"kind": "fill", "i": 3, "value": "7"}, {"kind": "click", "x": 10, "y": 20}]}))
    assert out["error"] == "field changed" and not out["completed"]
    p.mouse.click.assert_not_awaited()


def test_autonomous_rate_import_is_idempotent_and_refuses_a_changed_shipment(monkeypatch):
    api = FakeFiveU()
    kit.load(api)
    airline = kit.world().portal[("FRA", "ORD")][0]
    request = {"origin": "FRA", "destination": "ORD", "chargeable_kg": "320", "weight_kg": "320",
               "volume_cbm": "1", "pieces": 1, "pickup_zone": None, "pickup_postcode": None}
    store.put("deal-77", "deal", "pricing", {"root": 77, "request": request, "browser_request": request,
              "offers": [], "portal_missing": {"airlines": [airline], "weight_kg": "320"}})
    ctx = tools.Ctx(Forwarder(api), "session-77", "deal-77", 77, "customer", None)
    monkeypatch.setattr(tools, "_browser", lambda *a, **k: {"text": "1696.00 EUR · 1 day · R-autonomous77"})
    first = tools.browser(ctx, "save_rate", airline=airline["name"])
    second = tools.browser(ctx, "save_rate", airline=airline["name"])
    assert first["ok"] and second["already_saved"]
    assert first["priced_options"]["options"][0]["total"] == "1696.00 EUR"
    assert len(store.get("deal-77")["data"]["offers"]) == 1
    assert not store.get("deal-77")["data"].get("person_needed")
    store.update("deal-77", lambda r: (r["status"], {**r["data"], "request": {**request, "chargeable_kg": "500"}}))
    assert "shipment changed" in tools.browser(ctx, "save_rate", airline=airline["name"])["error"]
    store.update("deal-77", lambda r: (r["status"], {**r["data"], "request": request}))
    result = "Total\t1696.00\nCurrency\tEUR\nTransit days\t1\nrate_id\tR-lanecheck77\nLane\tFRA-JFK"
    monkeypatch.setattr(tools, "_browser", lambda *a, **k: {"text": result})
    assert "different lane" in tools.browser(ctx, "save_rate", airline=airline["name"])["error"]
    result = result.replace("FRA-JFK", "FRA-ORD") + "\nValid until\t2020-01-01T00:00:00+00:00"
    assert "expired" in tools.browser(ctx, "save_rate", airline=airline["name"])["error"]
    assert len(store.get("deal-77")["data"]["offers"]) == 1


def test_browser_image_reaches_the_same_agent_without_base64_in_event_logs(monkeypatch):
    image = "data:image/jpeg;base64,dGVzdA=="
    def turn(items, _):
        if items[-1].get("type") == "function_call_output":
            assert items[-1]["output"][1] == {"type": "input_image", "image_url": image, "detail": "high"}
            return []
        return [{"type": "function_call", "call_id": "see", "name": "browser", "arguments": '{"action":"look"}'}]
    llm.use_fake_turn(turn)
    monkeypatch.setattr(tools, "run", lambda *a, **k: {"text": "a visual check", "_image": image})
    agent.execute(Forwarder(FakeFiveU()), 88, "customer", mail=None, event="Inspect the page")
    assert image not in str(store.events())
    assert store.get("session-88")["status"] == "idle"


def test_portal_table_keeps_currency_days_and_weight_with_their_labels():
    text = "Your rate\nrate_id\tR-tGUQ2mU-DWkPimU0\nAirline\tBorealis Freight Airways (BX)\nLane\tFRA-ORD\nChargeable weight (kg)\t320\nTotal\t1171.20\nCurrency\tEUR\nTransit days\t1\nValid until\t2026-11-22T04:11:37+00:00"
    out = read_portal_page(text)
    assert out["total"] == "1171.20" and out["days"] == "1" and out["weight_kg"] == "320"
    assert out["lane"] == "FRA-ORD" and out["rate_id"] == "R-tGUQ2mU-DWkPimU0"
    assert read_portal_page(text.replace("1171.20", "1.171,20"))["total"] == "1171.20"
    assert read_portal_page(text.replace("EUR", "USD"))["total"] is None
    assert read_portal_page(text + "\nAnother rate R-different123")["rate_id"] is None
    assert read_portal_page("1171.20 EUR, 1 day, R-example1")["total"] == "1171.20"


def test_two_airlines_on_one_result_only_import_the_selected_eur_row(monkeypatch):
    api = FakeFiveU()
    kit.load(api)
    lane = ("CGN", "DEL")
    carriers = kit.world().portal[lane]
    first, second = carriers[:2]
    request = {"origin": lane[0], "destination": lane[1], "chargeable_kg": "320", "weight_kg": "320",
               "volume_cbm": "1", "pieces": 1, "pickup_zone": None, "pickup_postcode": None}
    store.put("deal-77", "deal", "pricing", {"root": 77, "request": request, "browser_request": request,
              "offers": [], "portal_missing": {"airlines": carriers, "weight_kg": "320"}})
    ctx = tools.Ctx(Forwarder(api), "session-77", "deal-77", 77, "customer", None)
    header = "rate_id\tAirline\tLane\tChargeable weight (kg)\tTotal\tCurrency\tTransit days"
    rows = [f"R-first123\t{first['name']}\tCGN-DEL\t320\t1.171,20\tEUR\t1",
            f"R-other123\t{second['name']}\tCGN-DEL\t320\t987.00\tUSD\t3"]
    monkeypatch.setattr(tools, "_browser", lambda *a: {"text": "\n".join([header, *rows])})

    def save(airline, ref=None):
        return tools.browser(ctx, "save_rate", airline=airline["code"], rate_id=ref)

    unresolved = save(first)
    assert len(unresolved["rate"]["candidates"]) == 2 and not unresolved["priced_options"]["options"]
    assert "different or unknown airline" in save(second, "R-first123")["error"]
    assert "USD" in save(second, "R-other123")["error"]
    assert not store.get("deal-77")["data"]["offers"]
    result = save(first, "R-first123")
    assert result["offer"]["total"] == "1171.20" and result["offer"]["days"] == "1"
    assert result["priced_options"]["portal_page"]["airlines"] == [f"{second['name']} ({second['code']})"]
    assert store.get("deal-77")["data"]["browser_activity"]["active"]
    assert save(first, "R-first123")["already_saved"]
    rows[:] = [rows[1].replace("USD", "EUR")]
    assert "longer displayed" in save(first, "R-first123")["error"]
    result = save(second, "R-other123")
    assert {o["bookable_reference"] for o in result["priced_options"]["options"]} == {"R-first123", "R-other123"}
    assert "portal_page" not in result["priced_options"]
    assert not store.get("deal-77")["data"]["browser_activity"]["active"]
    rows[0] = rows[0].replace("987.00", "700.00")
    assert "different rate details" in save(second, "R-other123")["error"]
    rows[0] = rows[0].replace("320", "42")
    assert "weight" in save(second, "R-other123")["error"]


def test_separate_cards_keep_amount_currency_and_reference_together():
    card_a = "rate_id: R-first123\nAirline: Example\nLane: CGN-DEL\nChargeable weight (kg): 100\nTotal: 120\nCurrency: USD\nTransit days: 1"
    card_b = card_a.replace("R-first123", "R-other123").replace("USD", "EUR").replace("120", "145")
    assert read_portal_page(card_a + "\n\n" + card_b, "R-first123")["total"] is None
    assert read_portal_page(card_a + "\n\n" + card_b, "R-other123")["total"] == "145"
    assert read_portal_page(card_a + "\n" + card_b, "R-other123")["ambiguous"]
    assert read_portal_page(card_a + "\n\n" + card_a)["ambiguous"]
    assert read_portal_page(card_a.replace("Currency: USD", "Currency: USD\nCurrency: EUR"))["ambiguous"]


def test_rate_service_backoff_sees_incoming_price_and_preserves_time_to_quote(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.forwarder import add_portal_page_rate

    api = FakeFiveU()
    kit.load(api)
    airline = kit.world().portal["FRA", "ORD"][0]
    req = {"origin": "FRA", "destination": "ORD", "chargeable_kg": "320", "weight_kg": "320",
           "volume_cbm": "1", "pieces": 1, "pickup_zone": None, "pickup_postcode": None}
    now = datetime.now(timezone.utc)
    store.put("deal-77", "deal", "pricing", {"root": 77, "request": req, "browser_request": req,
              "offers": [], "received_at": (now - timedelta(seconds=337)).isoformat(),
              "portal_missing": {"airlines": [airline], "weight_kg": "320"}})
    ctx = tools.Ctx(Forwarder(api), "session-77", "deal-77", 77, "customer", None)
    def incoming(seconds):
        assert seconds == 14
        add_portal_page_rate(ctx.deal_id, airline["name"], 1696, 1, "R-arrived", 320)
    sleep = Mock(side_effect=incoming)
    monkeypatch.setattr(tools.time, "sleep", sleep)
    lookup = lambda: tools.get_offers(ctx, shipment=None, preference="fastest", wait_seconds=60,
                                     supplier_retry_after_seconds=14)
    assert "retry_deferred" in lookup()
    sleep.assert_not_called()
    store.update(ctx.deal_id, lambda r: (r["status"], {**r["data"], "received_at": now.isoformat()}))
    result = lookup()
    sleep.assert_called_once_with(14)
    assert "portal_page" not in result and result["options"][0]["total"] == "1696.00 EUR"


def test_currency_picker_does_not_overrule_the_currency_of_the_result():
    text = "Available currencies: EUR USD\nTotal\t246.50\nCurrency\tEUR\nTransit days\t1\nrate_id\tR-currency01"
    assert read_portal_page(text)["total"] == "246.50"
    assert read_portal_page("Total USD 246.50, fee 2 EUR, 1 day, R-currency01")["total"] is None
