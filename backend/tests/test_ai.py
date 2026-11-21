import json
import sqlite3
from types import SimpleNamespace as NS

import httpx
import pytest

from app import store
from app.ai import budget, profiles, service
from app.ai.cost import cost_usd
from app.ai.errors import AiError
from app.ai.providers import AnthropicProvider, OpenAIProvider, normalize_anthropic
from app.ai.schema import strict_schema
from app.ai.types import AiModel, Instruction


def setup_function() -> None:
    store.use_connection(sqlite3.connect(":memory:", check_same_thread=False))


def test_cost_chat_completions_shape() -> None:
    u = NS(prompt_tokens=1000, completion_tokens=500, prompt_tokens_details=NS(cached_tokens=200))
    assert cost_usd("gpt-6-luna", u) == pytest.approx((800 * 0.1 + 500 * 0.5 + 200 * 0.01) / 1e6)


def test_cost_responses_shape() -> None:
    u = {"input_tokens": 3000, "output_tokens": 200, "input_tokens_details": {"cached_tokens": 1000}}
    assert cost_usd("gpt-6.1-sol", u) == pytest.approx((2000 * 2 + 200 * 10 + 1000 * 0.1) / 1e6)


def test_cost_anthropic_shape_with_long_cache() -> None:
    u = {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 2000,
         "cache_creation_input_tokens": 500, "cache_creation": {"ephemeral_1h_input_tokens": 100}}
    assert cost_usd("claude-sonnet-5-5", u) == pytest.approx((1000 * 2 + 100 * 10 + 2000 * 0.1 + 400 * 2.5 + 100 * 4) / 1e6)


def test_cost_unknown_is_none_not_a_guess() -> None:
    assert cost_usd("some-new-model", NS(prompt_tokens=1, completion_tokens=1, prompt_tokens_details=None)) is None
    assert cost_usd("gpt-6-luna", None) is None
    assert cost_usd("gpt-6-luna", {"input_tokens": -1, "output_tokens": 1}) is None


def test_strict_schema() -> None:
    s = strict_schema({"$schema": "x", "type": "object", "properties": {"a": {"type": "string"},
                       "b": {"type": "object", "properties": {"c": {"type": "number"}}}}})
    assert "$schema" not in s and s["required"] == ["a", "b"] and s["additionalProperties"] is False
    assert s["properties"]["b"]["required"] == ["c"]


def _openai_with(reply: dict, status: int = 200, seen: list | None = None) -> OpenAIProvider:
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(req.content))
        return httpx.Response(status, json=reply, headers={"x-request-id": "req_1"})
    return OpenAIProvider("sk-test", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_generate_structured_logs_tokens_and_cost() -> None:
    seen: list = []
    reply = {"model": "gpt-6-luna", "status": "completed",
             "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"price": 1968}'}]}],
             "usage": {"input_tokens": 1200, "output_tokens": 40, "input_tokens_details": {"cached_tokens": 1000}}}
    service.use_provider("openai", _openai_with(reply, seen=seen))
    res = service.generate_structured(AiModel("openai", "gpt-6-luna"), [Instruction("rules", cache=True)],
                                      {"mail": "2 pallets"}, {"type": "object", "properties": {"price": {"type": "number"}}},
                                      "quote")
    assert res.value == {"price": 1968} and res.response.request_id == "req_1"
    body = seen[0]
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert "prompt_cache_breakpoint" in body["input"][0]["content"][0]
    u = store.usage()
    assert u["llm_calls"] == 1 and u["cost_usd"] == pytest.approx((200 * 0.1 + 40 * 0.5 + 1000 * 0.01) / 1e6)


def test_generate_structured_errors_keep_response() -> None:
    service.use_provider("openai", _openai_with({"status": "completed", "output": []}, status=429))
    with pytest.raises(AiError) as e:
        service.generate_structured(AiModel("openai", "gpt-6-luna"), [], {}, {"type": "object"}, "x")
    assert e.value.code == "http" and e.value.status == 429


def test_anthropic_prepare_and_refusal() -> None:
    p = AnthropicProvider("k").prepare(AiModel("anthropic", "claude-sonnet-5-5"), [Instruction("r", cache=True)], {}, {}, "x")
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"} and p["fallbacks"] == "default"
    r = normalize_anthropic({"stop_reason": "refusal", "content": [], "usage": {"input_tokens": 3, "output_tokens": 0}})
    assert r.stop == "refusal" and r.usage is not None


def test_budget_stops_at_90_percent(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BUDGET_USD", "1")
    store.log("t", "llm", "call", cost_usd=0.85)
    budget.guard()  # 0.85 < 0.90
    store.log("t", "llm", "call", cost_usd=0.06)
    with pytest.raises(AiError) as e:
        budget.guard()
    assert e.value.code == "budget"


def test_stage_profiles(monkeypatch) -> None:
    assert profiles.stage("extraction").model == "gpt-6-luna"
    monkeypatch.setenv("LLM_WRITING_MODEL", "claude-sonnet-5-5")
    w = profiles.stage("writing")
    assert w.provider == "anthropic" and w.max_tokens == 4000
    monkeypatch.setenv("LLM_WRITING_MAX_TOKENS", "99999")
    with pytest.raises(AiError):
        profiles.stage("writing")
