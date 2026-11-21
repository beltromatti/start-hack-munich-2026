"""All settings come from the environment (.env in the repo root)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "docs" / "challenges" / "5u-kit"
load_dotenv(ROOT / ".env")


def _target() -> tuple[str | None, str]:
    """`gateway` (production: the only calls 5U scores) or `openai` (dev and tests: never counts as our spend)."""
    if os.getenv("LLM_TARGET", "gateway") == "openai":
        return None, os.getenv("OPENAI_API_KEY", "")
    return os.getenv("LLM_BASE_URL") or None, os.getenv("LLM_API_KEY", "")


@dataclass(frozen=True)
class Settings:
    fiveu_base_url: str = os.getenv("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
    fiveu_api_key: str = os.getenv("FIVEU_API_KEY", "")
    mailbox: str = os.getenv("FIVEU_MAILBOX", "start-milan@hackloop.mail")
    llm_base_url: str | None = _target()[0]
    llm_api_key: str = _target()[1]
    # One model per step. Parsing what a person wrote and writing to a person get the better small model.
    model_parse: str = os.getenv("LLM_MODEL_PARSE", "gpt-6-luna")
    model_bid: str = os.getenv("LLM_MODEL_BID", "gpt-5-nano")
    model_write: str = os.getenv("LLM_MODEL_WRITE", "gpt-6-luna")
    db_path: str = os.getenv("DB_PATH", str(ROOT / "backend" / "data" / "forwarder.db"))
    worker: bool = os.getenv("WORKER", "0") == "1"
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "1.5"))
    # How long we wait for carrier and trucker replies before quoting with what we have.
    bid_wait_seconds: float = float(os.getenv("BID_WAIT_SECONDS", "50"))
    persona: str = os.getenv("PERSONA_NAME", "Giulia")
    company: str = os.getenv("COMPANY_NAME", "START Milan Forwarding")


settings = Settings()
