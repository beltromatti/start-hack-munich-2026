import json
import sqlite3
from types import SimpleNamespace as NS

from app import agent, llm, store, worker
from app.channels.mail import FakeMail


def setup_function() -> None:
    store.use_connection(sqlite3.connect(":memory:", check_same_thread=False))


class FakeModel:
    """Returns scripted responses: first a tool call, then a final answer."""

    def __init__(self, replies: list) -> None:
        self.replies = replies
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        msg = self.replies.pop(0)
        return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=10, completion_tokens=5))


def tool_call(name: str, args: dict) -> NS:
    return NS(content=None, tool_calls=[NS(id="c1", function=NS(name=name, arguments=json.dumps(args)))])


def test_agent_calls_tool_logs_steps_and_counts_tokens() -> None:
    @agent.tool
    def best_rate(origin: str, weight_kg: float) -> dict:
        """Cheapest rate for a lane."""
        return {"carrier": "XX", "per_kg": 4.1, "origin": origin, "weight": weight_kg}

    fake = FakeModel([tool_call("best_rate", {"origin": "HKG", "weight_kg": 480}),
                      NS(content="Quote: 1968 USD", tool_calls=None)])
    llm.use_client(fake)

    res = agent.run("quote", "You quote freight.", "2 pallets HKG, 480 kg", [best_rate])

    assert res.answer == "Quote: 1968 USD" and res.steps == 2
    assert fake.calls[0]["tools"][0]["function"]["parameters"]["properties"]["weight_kg"]["type"] == "number"
    kinds = [e["kind"] for e in store.events(run_id=res.run_id)]
    assert kinds == ["start", "llm", "tool", "llm", "done"]
    assert store.usage() == {"tokens_in": 20, "tokens_out": 10, "llm_calls": 2}


def test_tool_error_goes_back_to_model() -> None:
    @agent.tool
    def boom() -> dict:
        """Always fails."""
        raise RuntimeError("portal down")

    llm.use_client(FakeModel([tool_call("boom", {}), NS(content="gave up", tool_calls=None)]))
    res = agent.run("t", "s", "task", [boom])
    assert res.answer == "gave up"
    assert any(e["kind"] == "error" and "portal down" in e["summary"] for e in store.events())


def test_ask_json_repairs_once() -> None:
    llm.use_client(FakeModel([NS(content="not json", tool_calls=None), NS(content='{"a": 1}', tool_calls=None)]))
    assert llm.ask_json("s", "u", agent="t") == {"a": 1}


def test_records_upsert_and_list() -> None:
    rid = store.upsert("quote", {"price": 100})
    store.upsert("quote", {"price": 120}, status="sent", id_=rid)
    [r] = store.records("quote")
    assert r["status"] == "sent" and r["data"] == {"price": 120}


def test_worker_routes_fake_mail(tmp_path) -> None:
    box = FakeMail(tmp_path)
    (tmp_path / "inbox" / "1.json").write_text(json.dumps({"from": "a@b.c", "subject": "Rate request", "body": "x"}))
    seen = []

    @worker.on("default")
    def handle(mail, b) -> None:
        seen.append(mail.subject)
        b.send(mail.sender, "Re: " + mail.subject, "hi")

    assert worker.tick(box) == 1 and seen == ["Rate request"]
    assert worker.tick(box) == 0  # not handled twice
    assert len(list((tmp_path / "outbox").glob("*.json"))) == 1
