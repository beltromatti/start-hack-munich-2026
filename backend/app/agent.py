"""The forwarder agent: one identity, one session per thread, as many executions as the thread needs.

A session is the deal's working memory: it lives in the register (restart-safe) and every new mail in the thread,
or a person writing into it, resumes it with the same prefix (identity, tools, the thread so far), so the provider
cache stays warm and the agent always has the whole deal in front of it.

The system keeps one constraint per execution, the required outcome (a mail answered, or a reasoned no-reply),
and one stop: an execution that turns 10 times in a row without anything succeeding. Everything else, how many
steps, which tools, how long the mail, is the model's.
"""
import json
import time
from datetime import datetime, timezone
from typing import Any

from . import docs, llm, store, tools
from .config import settings

SPINNING = 10


def on_mail(fw: Any, m: dict, kind: str) -> None:
    task = "tracking" if kind == "tracking" else "customer"
    execute(fw, m["root"], task, mail=m, event=_mail_event(fw, m))


def resume_inbox(fw: Any, inbox_id: str) -> None:
    """Messages for a session (a person on the team, or news from the system): the session resumes with them."""
    taken = store.update(inbox_id, lambda r: ("empty", {**r["data"], "items": [], "taken": r["data"]["items"]})
                         if r["status"] == "pending" else None)
    if not taken or taken["status"] != "empty" or not taken["data"].get("taken"):
        return
    s = store.get(taken["data"]["session"])
    if not s:
        return
    event = "\n\n".join(f"Update from the system ({t['at']}): {t['text']}" if t["who"] == "system" else
                          f"Message from {t['who']} (a person on our team, {t['at']}): {t['text']}"
                          for t in taken["data"]["taken"])
    execute(fw, s["data"]["root"], s["data"]["task"], mail=None, event=event)


def execute(fw: Any, root: int, task: str, *, mail: dict | None, event: str) -> None:
    sid, deal_id = f"session-{root}", f"deal-{root}"
    s = store.get(sid)
    if s is None:
        messages = [{"role": "system", "content": _system()},
                    {"role": "user", "content": f"{llm.prompt('tasks/' + task)}\n\n{_context()}\n\n{event}"}]
        s = {"root": root, "task": task, "messages": messages, "seen": [], "executions": 0}
    else:
        s = s["data"]
        _close_dangling(s["messages"])
        key = f"mail:{mail['id']}" if mail else None
        if key is None or key not in s["seen"]:
            s["messages"].append({"role": "user", "content": f"{_context()}\n\n{event}"})
    if mail and f"mail:{mail['id']}" not in s["seen"]:
        s["seen"].append(f"mail:{mail['id']}")
    s["executions"] += 1
    store.put(sid, "session", "running", s)
    ctx = tools.Ctx(fw, sid, deal_id, root, task, mail)
    if task == "customer":
        tools._ensure_deal(ctx)
    store.log("forwarder", "info", f"execution {s['executions']} ({task})", run_id=deal_id)

    failing, nudged = 0, False
    while True:
        turn = llm.chat(s["messages"], tools.TOOLS, model=settings.model_agent, effort=settings.effort_agent,
                        run_id=deal_id)
        s["messages"].append(turn)
        store.put(sid, "session", "running", s)
        calls = turn.get("tool_calls") or []
        if turn.get("content"):
            store.log("forwarder", "thought", turn["content"][:500], run_id=deal_id)
        if not calls:
            if mail is not None and not ctx.outcome and not nudged:
                nudged = True  # the one thing the system asks: this mail gets an answer, or a reasoned no-reply
                s["messages"].append({"role": "user", "content": (
                    "(system) The mail you are handling has not been answered yet. Send the answer with send_mail, "
                    "or call no_reply with the reason if nothing should be sent.")})
                continue
            if mail is not None and not ctx.outcome:
                store.log("forwarder", "error", "execution ended without answering the mail", run_id=deal_id)
            break
        ok = 0
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
                result = tools.run(ctx, name, args)
            except Exception as e:  # the model sees what went wrong and decides
                result = {"error": f"{type(e).__name__}: {e}"}
            ok += 0 if isinstance(result, dict) and "error" in result else 1
            store.log("forwarder", "tool", f"{name}({_short(c['function']['arguments'])})",
                      {"args": c["function"]["arguments"], "result": result}, run_id=deal_id)
            s["messages"].append({"role": "tool", "tool_call_id": c["id"],
                                  "content": json.dumps(result, default=str, ensure_ascii=False)})
            store.put(sid, "session", "running", s)
        failing = 0 if ok else failing + 1
        if failing >= SPINNING:
            store.log("forwarder", "error", f"stopped: {SPINNING} turns without progress", run_id=deal_id)
            break
    store.put(sid, "session", "idle", s)


def notify(session_id: str, text: str) -> None:
    """Something happened in the world that this deal should hear about (a booking confirmed)."""
    operator_message(session_id, text, who="system")


def operator_message(session_id: str, text: str, who: str = "operator") -> dict | None:
    """A person writes into a session (or the system has news for it); the loop resumes it. The inbox is a
    record of its own, so a message that arrives while the session works is never overwritten."""
    s = store.get(session_id)
    if not s:
        return None
    item = {"who": who, "text": text, "at": _now()}
    iid = f"inbox-{session_id}"
    with store._lock:
        rec = store.get(iid)
        items = (rec["data"]["items"] if rec else []) + [item]
        store.put(iid, "inbox", "pending", {"session": session_id, "root": s["data"]["root"], "items": items})
    return store.get(iid)


# ---- context -----------------------------------------------------------------------------------------------

def _system() -> str:
    return llm.prompt("forwarder").replace("{persona}", settings.persona).replace("{company}", settings.company)


def _context() -> str:
    return f"Now: {_now()}. Our mailbox: {settings.mailbox}."


def _now() -> str:
    t = datetime.now(timezone.utc)
    return t.strftime("%a %d %b %Y %H:%M:%S UTC")


def _mail_event(fw: Any, m: dict) -> str:
    text = (f"New mail in this thread: id {m['id']}, from {m['sender']}, at {m['received_at']}\n"
            f"Subject: {m['subject']}\n\n{m['body']}")
    for a in m.get("attachments") or []:
        try:
            text += f"\n\n[attachment {a.get('filename')}]\n" + docs.text(a.get("filename", ""),
                                                                          fw.api.attachment(m["id"], a.get("id")))
        except Exception as e:
            text += f"\n\n[attachment {a.get('filename')}: could not be read: {e!r}]"
    return text


def _close_dangling(messages: list[dict]) -> None:
    """After a restart mid-turn: every tool call gets a result, so the conversation stays valid."""
    last = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "assistant"), None)
    if last is None:
        return
    answered = {m.get("tool_call_id") for m in messages[last + 1:] if m.get("role") == "tool"}
    for c in messages[last].get("tool_calls") or []:
        if c["id"] not in answered:
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(
                {"error": "interrupted by a restart; the outcome is unknown. Check the deal before repeating it."})})


def _short(args: str) -> str:
    s = (args or "").replace("\n", " ")
    return s if len(s) < 160 else s[:157] + "..."
