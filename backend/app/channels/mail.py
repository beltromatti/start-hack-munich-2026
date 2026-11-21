"""Mail channel. Every challenge has a mailbox (5U: own mailbox API, Lio: supplier mailboxes,
revel8: email to targets). Write one adapter per challenge that implements MailAdapter.

FakeMail reads JSON files from backend/data/inbox/ and writes sent mail to backend/data/outbox/,
so the whole pipeline runs locally before we have API keys.
"""
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from ..config import ROOT


@dataclass
class Mail:
    id: str
    sender: str
    to: str
    subject: str
    body: str
    thread_id: str | None = None
    received_at: float = field(default_factory=time.time)
    attachments: list[str] = field(default_factory=list)  # local file paths


class MailAdapter(Protocol):
    def fetch_new(self) -> list[Mail]: ...
    def send(self, to: str, subject: str, body: str, thread_id: str | None = None) -> str: ...


class FakeMail:
    def __init__(self, base: Path = ROOT / "backend" / "data"):
        self.inbox, self.outbox = base / "inbox", base / "outbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.outbox.mkdir(parents=True, exist_ok=True)
        self.seen: set[str] = set()

    def fetch_new(self) -> list[Mail]:
        out = []
        for f in sorted(self.inbox.glob("*.json")):
            if f.name in self.seen:
                continue
            self.seen.add(f.name)
            d = json.loads(f.read_text())
            out.append(Mail(id=d.get("id", f.stem), sender=d["from"], to=d.get("to", "us@example.com"),
                            subject=d.get("subject", ""), body=d.get("body", ""), thread_id=d.get("thread_id")))
        return out

    def send(self, to: str, subject: str, body: str, thread_id: str | None = None) -> str:
        mid = f"out_{int(time.time() * 1000)}"
        (self.outbox / f"{mid}.json").write_text(json.dumps(
            asdict(Mail(id=mid, sender="us@example.com", to=to, subject=subject, body=body, thread_id=thread_id)),
            indent=2))
        return mid


def adapter(name: str) -> MailAdapter:
    if name == "fake":
        return FakeMail()
    raise ValueError(f"unknown MAIL_ADAPTER {name!r}: add it in channels/mail.py")
