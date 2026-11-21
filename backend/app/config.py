"""All settings come from the environment (.env in the repo root or backend/)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env")


@dataclass(frozen=True)
class Settings:
    # Any OpenAI-compatible endpoint: OpenAI, a challenge LLM gateway, OpenRouter, a local model.
    llm_base_url: str | None = os.getenv("LLM_BASE_URL") or None
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-6-luna")
    db_path: str = os.getenv("DB_PATH", str(ROOT / "backend" / "data" / "hack.db"))
    # Background worker: polls the channels every N seconds when WORKER=1.
    worker: bool = os.getenv("WORKER", "0") == "1"
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "20"))
    mail_adapter: str = os.getenv("MAIL_ADAPTER", "fake")  # fake | <challenge adapter>


settings = Settings()
