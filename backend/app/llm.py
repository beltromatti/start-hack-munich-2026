"""One place for model calls, so every call is logged with its tokens.

Works with any OpenAI-compatible endpoint (set LLM_BASE_URL). Some challenges score token cost or
require their own gateway, so never call a model directly from elsewhere.
"""
import json
from typing import Any, Protocol

from openai import OpenAI

from . import store
from .ai import budget
from .ai.cost import cost_usd
from .config import settings


class ChatClient(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


_client: ChatClient | None = None


def client() -> ChatClient:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "missing").chat.completions
    return _client


def use_client(c: ChatClient) -> None:
    """Tests: swap in a fake."""
    global _client
    _client = c


def chat(messages: list[dict], *, agent: str, run_id: str | None = None, tools: list[dict] | None = None,
         model: str | None = None, json_mode: bool = False, **kwargs: Any) -> Any:
    """Returns the assistant message object and logs one `llm` event with token usage."""
    args: dict[str, Any] = {"model": model or settings.llm_model, "messages": messages, **kwargs}
    if tools:
        args["tools"] = tools
    if json_mode:
        args["response_format"] = {"type": "json_object"}
    budget.guard()
    res = client().create(**args)
    u = getattr(res, "usage", None)
    msg = res.choices[0].message
    store.log(agent, "llm", f"{args['model']}: {_preview(msg)}", run_id=run_id,
              tokens_in=getattr(u, "prompt_tokens", 0) or 0, tokens_out=getattr(u, "completion_tokens", 0) or 0,
              cost_usd=cost_usd(args["model"], u))
    return msg


def ask_json(system: str, user: str, *, agent: str, run_id: str | None = None, retries: int = 1) -> dict:
    """Ask for a JSON object; one repair retry if the model returns something unparsable."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(retries + 1):
        msg = chat(messages, agent=agent, run_id=run_id, json_mode=True)
        try:
            out = json.loads(msg.content or "")
            if isinstance(out, dict):
                return out
        except json.JSONDecodeError:
            pass
        messages += [{"role": "assistant", "content": msg.content or ""},
                     {"role": "user", "content": "That was not one valid JSON object. Reply with the JSON object only."}]
    store.log(agent, "error", "model returned no valid JSON", run_id=run_id)
    raise ValueError("model returned no valid JSON")


def _preview(msg: Any) -> str:
    calls = getattr(msg, "tool_calls", None)
    if calls:
        return "calls " + ", ".join(c.function.name for c in calls)
    return (msg.content or "").replace("\n", " ")[:160]
