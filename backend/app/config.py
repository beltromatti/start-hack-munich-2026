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
    # The forwarder agent, and the small model that reads carrier replies and tariffs for the tools.
    model_agent: str = os.getenv("LLM_MODEL_AGENT", "gpt-6-luna")
    effort_agent: str = os.getenv("LLM_EFFORT_AGENT", "low")
    model_bid: str = os.getenv("LLM_MODEL_BID", "gpt-5-nano")
    model_tariff: str = os.getenv("LLM_MODEL_TARIFF", "gpt-6-luna")
    db_path: str = os.getenv("DB_PATH", str(ROOT / "backend" / "data" / "forwarder.db"))
    worker: bool = os.getenv("WORKER", "0") == "1"
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "1.5"))
    # How long get_offers waits for carrier and trucker replies by default (the agent may ask for less or more).
    bid_wait_seconds: float = float(os.getenv("BID_WAIT_SECONDS", "85"))
    persona: str = os.getenv("PERSONA_NAME", "Giulia")
    company: str = os.getenv("COMPANY_NAME", "START Milan Forwarding")

    @staticmethod
    def effort_for(model: str) -> str | None:
        """Extraction calls: as little thinking as the model allows (they read, they do not decide)."""
        if model.startswith(("gpt-6", "gpt-5.6")):
            return "none"
        if model.startswith("gpt-5"):
            return "minimal"
        return None


settings = Settings()
