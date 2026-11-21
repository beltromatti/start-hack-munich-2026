"""The loop that keeps agents running all night: poll channels, route each item, handle it.

Register handlers with @on("kind"). route() decides the kind; replace it with an LLM router or rules
once we know the challenge. One failing item never stops the loop.
"""
import asyncio
from typing import Callable

from . import store
from .channels.mail import Mail, MailAdapter, adapter
from .config import settings

Handler = Callable[[Mail, MailAdapter], None]
_handlers: dict[str, Handler] = {}


def on(kind: str) -> Callable[[Handler], Handler]:
    def wrap(fn: Handler) -> Handler:
        _handlers[kind] = fn
        return fn
    return wrap


def route(mail: Mail) -> str:
    """Placeholder router. Challenge code overrides this (keywords first, LLM only if unclear)."""
    return "default"


@on("default")
def _log_only(mail: Mail, box: MailAdapter) -> None:
    store.log("router", "info", f"no handler yet for: {mail.subject}", {"from": mail.sender})


def tick(box: MailAdapter) -> int:
    handled = 0
    for mail in box.fetch_new():
        kind = route(mail)
        store.log("router", "decision", f"{mail.subject[:80]} -> {kind}", {"mail_id": mail.id, "from": mail.sender})
        try:
            _handlers.get(kind, _handlers["default"])(mail, box)
            handled += 1
        except Exception as e:
            store.log("router", "error", f"{kind} failed on {mail.id}: {e}")
    return handled


async def loop() -> None:
    box = adapter(settings.mail_adapter)
    store.log("worker", "info", f"worker started, polling every {settings.poll_seconds}s via {settings.mail_adapter}")
    while True:
        try:
            await asyncio.to_thread(tick, box)
        except Exception as e:
            store.log("worker", "error", f"tick failed: {e}")
        await asyncio.sleep(settings.poll_seconds)
