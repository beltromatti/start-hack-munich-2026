"""Every model call goes through here: one OpenAI-compatible client (the 5U gateway in production), tokens and
USD cost logged per call.

The forwarder agent runs on the Responses API (tools with reasoning, stateless: we keep the items, encrypted
reasoning included, in the register). The small extraction calls for the tools run on Chat Completions.

A model that does not answer is not a failure: the call waits and runs again (transient errors; the gateway down:
OpenAI directly as a last resort). Only a request the provider will never accept (400, 422) fails at once.
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
    "gpt-6-sol": (2.00, 0.20, 10.00), "gpt-6.2-sol": (2.00, 0.10, 10.00), "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5.4": (2.50, 0.25, 15.00), "gpt-5": (1.25, 0.125, 10.00), "gpt-5.1": (1.25, 0.125, 10.00),
}
# Real context windows (tokens): a session is never cut short by a number of ours.
CONTEXT = {"gpt-6": 1_050_000, "gpt-5.6": 1_050_000, "gpt-5": 400_000, "gpt-4.1": 1_047_576}
WAITS = [1, 3, 10, 30, 60]  # seconds between attempts once the gateway and OpenAI both fail

_client: OpenAI | None = None
_direct: OpenAI | None = None
_fake: Callable[..., dict] | None = None
_fake_turn: Callable[..., list] | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "missing", timeout=120,
                         max_retries=2)
    return _client


def direct() -> OpenAI | None:
    """OpenAI without the gateway: a last resort when the gateway is down (the call loses its cost points but
    the request is answered)."""
    global _direct
    key = os.getenv("OPENAI_API_KEY")
    if _direct is None and key and settings.llm_base_url:
        _direct = OpenAI(api_key=key, timeout=120, max_retries=1)
    return _direct


def use_fake(fn: Callable[..., dict] | None) -> None:
    """Tests: extraction calls. fn(name, system, user, schema) -> dict."""
    global _fake
    _fake = fn


def use_fake_turn(fn: Callable[..., list] | None) -> None:
    """Tests: agent turns. fn(items, tools) -> output items (function_call / message), as the Responses API."""
    global _fake_turn
    _fake_turn = fn


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def context_window(model: str) -> int:
    return next((v for k, v in CONTEXT.items() if model.startswith(k)), 128_000)


def cost(model: str, tokens_in: int, cached: int, tokens_out: int) -> float | None:
    p = PRICES.get(model)
    if p is None:
        return None
    return ((tokens_in - cached) * p[0] + cached * p[1] + tokens_out * p[2]) / 1e6


def _call(args: dict, label: str, run_id: str | None, agent: str, api: str = "chat") -> Any:
    """One request, waiting through anything transient. `api`: chat (Chat Completions) or responses."""
    t, attempt = time.time(), 0
    while True:
        c = client() if attempt < 2 or direct() is None else direct()
        try:
            res = c.responses.create(**args) if api == "responses" else c.chat.completions.create(**args)
            via = " DIRECT (gateway down)" if c is _direct else ""
            u = res.usage
            if api == "responses":
                tin, tout = u.input_tokens, u.output_tokens
                cached = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
                reasoning = getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0
            else:
                tin, tout = u.prompt_tokens, u.completion_tokens
                cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
                reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
            store.log(agent, "llm", f"{args['model']} [{label}] {time.time() - t:.1f}s{via}",
                      {"cached": cached, "reasoning": reasoning}, run_id=run_id, tokens_in=tin or 0,
                      tokens_out=tout or 0, cost_usd=cost(args["model"], tin or 0, cached, tout or 0))
            return res
        except (openai.BadRequestError, openai.UnprocessableEntityError) as e:  # never accepted: fail this request
            store.log(agent, "error", f"{args['model']} [{label}] rejected: {e!r}"[:500], run_id=run_id)
            raise
        except Exception as e:  # network, 429, 5xx, timeout: wait and run the same step again
            store.log(agent, "error", f"{args['model']} [{label}] attempt {attempt + 1}: {e!r}"[:400], run_id=run_id)
            if attempt >= 3:
                time.sleep(WAITS[min(attempt - 3, len(WAITS) - 1)])
            attempt += 1


def respond(instructions: str, items: list[dict], tools: list[dict], *, model: str, effort: str | None,
            run_id: str | None, agent: str = "forwarder") -> list[dict]:
    """One agent turn on the Responses API, stateless: the items (encrypted reasoning included) live in the
    register, so a session survives restarts and the next turn continues the same line of thought."""
    if _fake_turn is not None:
        out = _fake_turn(items, tools)
        store.log(agent, "llm", "fake turn", None, run_id=run_id)
        return out
    args: dict[str, Any] = {"model": model, "instructions": instructions, "input": items, "tools": tools,
                            "store": False, "include": ["reasoning.encrypted_content"], "parallel_tool_calls": True}
    if effort:
        args["reasoning"] = {"effort": effort}
    res = _call(args, "turn", run_id, agent, api="responses")
    return [i.model_dump(exclude_none=True) for i in res.output]


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
    res = _call(args, name, run_id, agent)
    return json.loads(res.choices[0].message.content or "{}")


def look(mime: str, raw: bytes, *, run_id: str | None = None) -> str:
    """What a picture says, as text (a scanned packing list, a photo of an offer, a label): through the gateway,
    with the tariff reader's model. The text then goes wherever the mail goes (the agent, the bid reader)."""
    if _fake is not None:
        return "[picture read by the fake model]"
    model = settings.model_tariff
    args: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": _content(prompt("look"),
                                                                                             [(mime, raw)])}]}
    e = settings.effort_for(model)
    if e:
        args["reasoning_effort"] = e
    res = _call(args, "look", run_id, "docs")
    return res.choices[0].message.content or ""


def transcribe(raw: bytes, filename: str, *, run_id: str | None = None) -> str:
    """Speech to text. The gateway takes no audio (probed Sat 22:40: no audio model, chat takes text and images
    only); 5U said to transcribe with a call of our own and use the text through the gateway as usual. So this is
    OpenAI directly, and never part of the gateway spend."""
    if _fake is not None:
        return "[voice message transcribed by the fake model]"
    c = direct()
    if c is None:
        raise RuntimeError("no OpenAI key for transcription")
    import io
    for attempt in range(3):
        try:
            f = io.BytesIO(raw)
            f.name = filename or "voice.mp3"
            t = time.time()
            text = c.audio.transcriptions.create(  # numbers as digits: the code reads them (round 69: "seven hours")
                model="gpt-4o-mini-transcribe", file=f,
                prompt="Write every number as digits: amounts like 340.60 euros, weights like 1410 kilos, times like "
                       "7 hours, postcodes like 51252, dates like 24 November.").text
            store.log("docs", "llm", f"gpt-4o-mini-transcribe [transcribe] {time.time() - t:.1f}s DIRECT, not gateway",
                      {"chars": len(text)}, run_id=run_id)
            return text
        except (openai.BadRequestError, openai.UnprocessableEntityError):
            raise
        except Exception as e:
            store.log("docs", "error", f"transcribe attempt {attempt + 1}: {e!r}"[:300], run_id=run_id)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("transcription unavailable")


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
