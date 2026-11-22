"""The forwarder agent: one identity, one session per thread, as many executions as the thread needs.

A session is the deal's working memory: its items (mails, tool calls and results, the model's encrypted
reasoning) live in the register, so it survives restarts, and every new mail in the thread, or a person writing
into it, resumes it with the same prefix: the provider cache stays warm and the agent has the whole deal at hand.

The system keeps one constraint per execution, the required outcome (a mail answered, or a reasoned no-reply),
and one stop: an execution that turns 10 times in a row without anything succeeding. Everything else, how many
steps, which tools, how long the mail, is the model's.
"""
import json
import time
from datetime import datetime, timezone
from typing import Any

from . import language, docs, llm, store, tools
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
    rec = store.get(sid)
    if rec is None or "items" not in rec["data"]:
        earlier = _earlier(root, mail)  # a thread that started before this session (a restart, a migration)
        known = _customer_notes(root, mail) if task == "customer" else ""
        s = {"root": root, "task": task, "seen": [], "executions": 0,
             "items": [_user(f"{llm.prompt('tasks/' + task)}\n\n{_context()}\n\n{known}{earlier}{event}")]}
    else:
        s = rec["data"]
        _close_dangling(s["items"])
        if not (mail and f"mail:{mail['id']}" in s["seen"]):
            s["items"].append(_user(f"{_context()}\n\n{event}"))
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
        out = llm.respond(_system(), s["items"], tools.TOOLS, model=settings.model_agent,
                          effort=settings.effort_agent, run_id=deal_id)
        s["items"].extend(out)
        store.put(sid, "session", "running", s)
        text = _text(out)
        if text:
            store.log("forwarder", "thought", text[:500], run_id=deal_id)
        calls = [i for i in out if i.get("type") == "function_call"]
        if not calls:
            if mail is not None and not ctx.outcome and not nudged:
                nudged = True  # the one thing the system asks: this mail gets an answer, or a reasoned no-reply
                s["items"].append(_user("(system) The mail you are handling has not been answered yet. Send the "
                                        "answer with send_mail, or call no_reply with the reason if nothing "
                                        "should be sent."))
                continue
            if mail is not None and not ctx.outcome:
                store.log("forwarder", "error", "execution ended without answering the mail", run_id=deal_id)
            break
        ok = 0
        for c in calls:
            try:
                result = tools.run(ctx, c["name"], json.loads(c.get("arguments") or "{}"))
            except Exception as e:  # the model sees what went wrong and decides
                result = {"error": f"{type(e).__name__}: {e}"}
            ok += 0 if isinstance(result, dict) and "error" in result else 1
            store.log("forwarder", "tool", f"{c['name']}({_short(c.get('arguments'))})",
                      {"args": c.get("arguments"), "result": result}, run_id=deal_id)
            s["items"].append({"type": "function_call_output", "call_id": c["call_id"],
                               "output": json.dumps(result, default=str, ensure_ascii=False)})
            store.put(sid, "session", "running", s)
        failing = 0 if ok else failing + 1
        if ctx.done and (mail is None or ctx.outcome):  # the model said it is done, and the mail is answered:
            break  # no closing call (each one costs points); the journal already shows what it did
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
    return datetime.now(timezone.utc).strftime("%a %d %b %Y %H:%M:%S UTC")


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _text(out: list[dict]) -> str:
    return "".join(c.get("text", "") for i in out if i.get("type") == "message"
                   for c in i.get("content") or [] if c.get("type") == "output_text").strip()


def lookalike(sender: str) -> str | None:
    """A customer we know whose address this one imitates ('weidner.spielwaren@' for 'weidner-spielwaren@', rounds
    105-106: 'my old mailbox is closing, send the offer here'). A fact for the agent, not a rule."""
    import re
    s = (sender or "").lower()
    norm = lambda a: re.sub(r"[^a-z0-9@]", "", a)
    known = {(r["data"].get("customer") or "").lower() for r in store.records("deal")} - {"", s, "tracking@hackloop.mail"}
    return next((k for k in sorted(known) if norm(k) == norm(s)), None)


def _mail_event(fw: Any, m: dict) -> str:
    lang = language.language_of(m["body"])  # a fact for the agent, not a rule: it still writes the mail
    twin = lookalike(m["sender"])
    text = (f"New mail in this thread: id {m['id']}, from {m['sender']}, at {m['received_at']}\n"
            + (f"Their own words are in {lang}.\n" if lang else "")
            + (f"This address is not on file; it imitates {twin}, a customer we know.\n" if twin else "")
            + f"Subject: {m['subject']}\n\n{m['body']}")
    for a in m.get("attachments") or []:
        try:
            text += f"\n\n[attachment {a.get('filename')}]\n" + docs.text(
                a.get("filename", ""), fw.api.attachment(m["id"], a.get("id")), run_id=f"deal-{m.get('root')}")
        except Exception as e:
            text += f"\n\n[attachment {a.get('filename')}: could not be read: {e!r}]"
    return text


def _earlier(root: int, mail: dict | None) -> str:
    prior = [x for x in store.thread(root) if not mail or x["id"] != mail["id"]]
    if not prior:
        return ""
    lines = [f"--- mail {x['id']} {'from us' if x['direction'] == 'out' else 'from ' + x['sender']} at "
             f"{x['received_at']}\nSubject: {x['subject']}\n\n{x['body']}" for x in prior]
    return "Earlier in this thread:\n\n" + "\n\n".join(lines) + "\n\n"


def _customer_notes(root: int, mail: dict | None) -> str:
    """What we noted in this customer's earlier deals: a wish that holds for their later requests (an airline they
    refuse, round 42) lives in those notes, and a new thread is a new session. The agent judges what still applies."""
    who = (mail or {}).get("sender")
    if not who:
        return ""
    notes = []
    for rec in store.records("deal"):
        d = rec["data"]
        if d.get("customer") == who and d.get("root") != root:
            notes += [(n.get("at", 0), d.get("subject") or rec["id"], n["text"]) for n in d.get("notes", [])]
    if not notes:
        return ""
    lines = [f"- {time.strftime('%d %b %H:%M', time.localtime(at))} ({subject}): {text}"
             for at, subject, text in sorted(notes, reverse=True)[:8]]
    return "Our notes from this customer's earlier deals (what still applies is your call):\n" + "\n".join(lines) + "\n\n"


def _close_dangling(items: list[dict]) -> None:
    """After a restart mid-turn: every tool call gets an output, so the session stays valid."""
    answered = {i.get("call_id") for i in items if i.get("type") == "function_call_output"}
    for i in [i for i in items if i.get("type") == "function_call" and i.get("call_id") not in answered]:
        items.append({"type": "function_call_output", "call_id": i["call_id"], "output": json.dumps(
            {"error": "interrupted by a restart; the outcome is unknown. Check the deal before repeating it."})})


def _short(args: str | None) -> str:
    s = (args or "").replace("\n", " ")
    return s if len(s) < 160 else s[:157] + "..."
