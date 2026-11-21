"""Every model call goes through here: one OpenAI-compatible client (the 5U gateway in production), tokens and
USD cost logged per call.

A model that does not answer is not a failure: the call waits and runs again (transient errors, the gateway down:
OpenAI directly as a last resort). Only a request the provider will never accept (400, 413, 422) fails at once.
"""
import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import openai
from openai import OpenAI

from . import store
from .config import settings

PROMPTS = Path(__file__).parent / "prompts"

# USD per million tokens: input, cached input, output (OpenAI list prices, Nov 2026).
PRICES = {
    "gpt-6-luna": (0.10, 0.01, 0.50), "gpt-5-nano": (0.05, 0.005, 0.40), "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5-mini": (0.25, 0.025, 2.00), "gpt-5.6-luna": (0.20, 0.02, 1.20), "gpt-4.1-nano": (0.10, 0.03, 0.40),
    "gpt-4.1-mini": (0.40, 0.10, 1.60), "gpt-4o-mini": (0.15, 0.075, 0.60), "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6-sol": (2.00, 0.20, 10.00), "gpt-6.2-sol": (2.00, 0.10, 10.00),
}
# Real context windows (tokens), so a long session is never cut short by a number of ours.
CONTEXT = {"gpt-6": 1_050_000, "gpt-5.6": 1_050_000, "gpt-5": 400_000, "gpt-4.1": 1_047_576}
WAITS = [1, 3, 10, 30, 60]  # seconds between attempts once the gateway and OpenAI both fail

_client: OpenAI | None = None
_direct: OpenAI | None = None
_fake: Callable[..., dict] | None = None
_fake_chat: Callable[..., dict] | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "missing", timeout=90,
                         max_retries=2)
    return _client


def direct() -> OpenAI | None:
    """OpenAI without the gateway: a last resort when the gateway is down (the call loses its cost points but
    the request is answered)."""
    global _direct
    key = os.getenv("OPENAI_API_KEY")
    if _direct is None and key and settings.llm_base_url:
        _direct = OpenAI(api_key=key, timeout=90, max_retries=1)
    return _direct


def use_fake(fn: Callable[..., dict] | None) -> None:
    """Tests: structured calls. fn(name, system, user, schema) -> dict."""
    global _fake
    _fake = fn


def use_fake_chat(fn: Callable[..., dict] | None) -> None:
    """Tests: agent turns. fn(messages, tools) -> assistant message dict."""
    global _fake_chat
    _fake_chat = fn


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def context_window(model: str) -> int:
    return next((v for k, v in CONTEXT.items() if model.startswith(k)), 128_000)


def cost(model: str, usage: Any) -> float | None:
    p = PRICES.get(model)
    if p is None or usage is None:
        return None
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    fresh = (usage.prompt_tokens or 0) - cached
    return (fresh * p[0] + cached * p[1] + (usage.completion_tokens or 0) * p[2]) / 1e6


def _call(args: dict, label: str, run_id: str | None, agent: str) -> tuple[Any, Any]:
    """One completion, waiting through anything transient. Returns (response, usage)."""
    t, attempt = time.time(), 0
    while True:
        c = client() if attempt < 2 or direct() is None else direct()
        try:
            res = c.chat.completions.create(**args)
            via = " DIRECT (gateway down)" if c is _direct else ""
            u = res.usage
            store.log(agent, "llm", f"{args['model']} [{label}] {time.time() - t:.1f}s{via}", None, run_id=run_id,
                      tokens_in=getattr(u, "prompt_tokens", 0) or 0, tokens_out=getattr(u, "completion_tokens", 0) or 0,
                      cost_usd=cost(args["model"], u))
            return res, u
        except (openai.BadRequestError, openai.UnprocessableEntityError) as e:  # never accepted: fail this request
            store.log(agent, "error", f"{args['model']} [{label}] rejected: {e!r}"[:500], run_id=run_id)
            raise
        except Exception as e:  # network, 429, 5xx, timeout: wait and run the same step again
            store.log(agent, "error", f"{args['model']} [{label}] attempt {attempt + 1}: {e!r}"[:400], run_id=run_id)
            if attempt >= 3:
                time.sleep(WAITS[min(attempt - 3, len(WAITS) - 1)])
            attempt += 1


def chat(messages: list[dict], tools: list[dict], *, model: str, effort: str | None, run_id: str | None,
         agent: str = "forwarder") -> dict:
    """One agent turn. Returns the assistant message as a plain dict (content, tool_calls)."""
    if _fake_chat is not None:
        msg = _fake_chat(messages, tools)
        store.log(agent, "llm", "fake turn", None, run_id=run_id)
        return msg
    args: dict[str, Any] = {"model": model, "messages": messages, "tools": tools, "parallel_tool_calls": True}
    if effort:
        args["reasoning_effort"] = effort
    res, _ = _call(args, "turn", run_id, agent)
    m = res.choices[0].message
    out: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
    if m.tool_calls:
        out["tool_calls"] = [{"id": c.id, "type": "function",
                              "function": {"name": c.function.name, "arguments": c.function.arguments}}
                             for c in m.tool_calls]
    return out


def structured(name: str, system: str, user: str, schema: dict, *, model: str, run_id: str | None = None,
               agent: str = "llm", images: list[tuple[str, bytes]] | None = None,
               effort: str | None = "default") -> dict:
    """One extraction: a JSON object that matches `schema`. `images`: (mime, bytes), e.g. a scanned tariff."""
    if _fake is not None:
        out = _fake(name, system, user, schema)
        store.log(agent, "llm", f"fake [{name}]", {"out": out}, run_id=run_id)
        return out
    args: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": _content(user, images)}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    e = settings.effort_for(model) if effort == "default" else effort
    if e:
        args["reasoning_effort"] = e
    res, _ = _call(args, name, run_id, agent)
    return json.loads(res.choices[0].message.content or "{}")


def _content(text: str, images: list[tuple[str, bytes]] | None) -> Any:
    if not images:
        return text
    return [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(raw).decode()}"}}
        for mime, raw in images]


def strict(properties: dict, required: list[str] | None = None) -> dict:
    """Schema helper: an object where every property is required (OpenAI strict mode), nullables via type lists."""
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": required or list(properties)}
