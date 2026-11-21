"""A deliberately small tool-calling loop. The model decides, tools act, every step is logged.

Define tools with @tool and pass them to run(). Keep business rules (prices, limits, who may be
emailed) in tool code, not in prompts.
"""
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

from . import llm, store

_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict

    def schema(self) -> dict:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def tool(fn: Callable[..., Any]) -> Tool:
    """Build a tool from a typed Python function; the docstring is the description."""
    hints = get_type_hints(fn)
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {"type": _TYPES.get(hints.get(name, str), "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return Tool(fn.__name__, (fn.__doc__ or fn.__name__).strip(), fn,
                {"type": "object", "properties": props, "required": required})


@dataclass
class Result:
    run_id: str
    answer: str
    steps: int


def run(agent: str, system: str, task: str, tools: list[Tool] | None = None, *, max_steps: int = 8,
        run_id: str | None = None) -> Result:
    run_id = run_id or store.new_id("run_")
    tools = tools or []
    by_name = {t.name: t for t in tools}
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    store.log(agent, "start", task[:300], run_id=run_id)
    for step in range(1, max_steps + 1):
        msg = llm.chat(messages, agent=agent, run_id=run_id, tools=[t.schema() for t in tools] or None)
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            store.log(agent, "done", (msg.content or "")[:300], run_id=run_id)
            return Result(run_id, msg.content or "", step)
        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in calls]})
        for c in calls:
            messages.append({"role": "tool", "tool_call_id": c.id,
                             "content": _call(agent, run_id, by_name.get(c.function.name), c)})
    store.log(agent, "error", f"stopped after {max_steps} steps", run_id=run_id)
    return Result(run_id, "", max_steps)


def _call(agent: str, run_id: str, t: Tool | None, call: Any) -> str:
    name = call.function.name
    if t is None:
        store.log(agent, "error", f"unknown tool {name}", run_id=run_id)
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        args = json.loads(call.function.arguments or "{}")
        out = t.fn(**args)
        store.log(agent, "tool", f"{name}({_short(args)})", {"args": args, "result": out}, run_id=run_id)
        return json.dumps(out, default=str)
    except Exception as e:  # the model sees the error and can recover
        store.log(agent, "error", f"{name} failed: {e}", {"args": call.function.arguments}, run_id=run_id)
        return json.dumps({"error": str(e)})


def _short(args: dict) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return s if len(s) < 120 else s[:117] + "..."
