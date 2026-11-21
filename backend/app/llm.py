"""Every model call goes through here: one OpenAI-compatible client (the 5U gateway in production),
strict JSON schema output, tokens and USD cost logged per call.

The model reads and writes language. It never decides a number that reaches a customer (see pricing.py).
"""
import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from . import store
from .config import settings

PROMPTS = Path(__file__).parent / "prompts"

# USD per million tokens: input, cached input, output (OpenAI list prices, Nov 2026).
PRICES = {
    "gpt-6-luna": (0.10, 0.01, 0.50), "gpt-5-nano": (0.05, 0.005, 0.40), "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5-mini": (0.25, 0.025, 2.00), "gpt-5.6-luna": (0.20, 0.02, 1.20), "gpt-4.1-nano": (0.10, 0.03, 0.40),
    "gpt-4.1-mini": (0.40, 0.10, 1.60), "gpt-4o-mini": (0.15, 0.075, 0.60), "gpt-6.1-terra": (1.00, 0.05, 5.00),
}
# Reasoning effort per model family: as little thinking as the task allows (cost and time are scored).
EFFORT = {"gpt-6": "none", "gpt-5.6": "none", "gpt-5": "minimal"}

_client: OpenAI | None = None
_direct: OpenAI | None = None
_fake: Callable[..., dict] | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "missing", timeout=40,
                         max_retries=2)
    return _client


def direct() -> OpenAI | None:
    """OpenAI without the gateway: only a last resort when the gateway is down (that quote loses its cost points,
    but keeps accuracy and time, which beats losing the request)."""
    global _direct
    key = os.getenv("OPENAI_API_KEY")
    if _direct is None and key and settings.llm_base_url:
        _direct = OpenAI(api_key=key, timeout=40, max_retries=1)
    return _direct


def use_fake(fn: Callable[..., dict] | None) -> None:
    """Tests: fn(name, system, user, schema) -> dict."""
    global _fake
    _fake = fn


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def cost(model: str, usage: Any) -> float | None:
    p = PRICES.get(model)
    if p is None or usage is None:
        return None
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    fresh = (usage.prompt_tokens or 0) - cached
    return (fresh * p[0] + cached * p[1] + (usage.completion_tokens or 0) * p[2]) / 1e6


def structured(name: str, system: str, user: str, schema: dict, *, model: str, run_id: str | None = None,
               agent: str = "llm", images: list[tuple[str, bytes]] | None = None) -> dict:
    """One call, one JSON object that matches `schema` (strict). `images`: (mime, bytes), e.g. a scanned tariff."""
    if _fake is not None:
        out = _fake(name, system, user, schema)
        store.log(agent, "llm", f"fake [{name}]", {"out": out}, run_id=run_id)
        return out
    args: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": _content(user, images)}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    effort = next((v for k, v in EFFORT.items() if model.startswith(k)), None)
    if effort:
        args["reasoning_effort"] = effort
    t = time.time()
    last: Exception | None = None
    for attempt, c in enumerate([client(), client(), direct()]):
        if c is None:
            continue
        try:
            res = c.chat.completions.create(**args)
            msg = res.choices[0].message
            out = json.loads(msg.content or "")
            u = res.usage
            via = " DIRECT (gateway down)" if attempt == 2 else ""
            store.log(agent, "llm", f"{model} [{name}] {time.time() - t:.1f}s{via}", {"out": out}, run_id=run_id,
                      tokens_in=getattr(u, "prompt_tokens", 0) or 0, tokens_out=getattr(u, "completion_tokens", 0) or 0,
                      cost_usd=cost(model, u))
            return out
        except Exception as e:  # network, refusal, bad JSON: retry, then the direct fallback, then the caller decides
            last = e
            store.log(agent, "error", f"{model} [{name}] failed: {e!r}"[:400], run_id=run_id)
    raise RuntimeError(f"model call {name} failed: {last!r}")


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
