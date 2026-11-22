"""The voice desk: without a key the page falls back to the browser, with one the calls go to ElevenLabs as asked."""
import pytest
from fastapi.testclient import TestClient

from app import voice
from app.main import app


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    voice._used.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


def test_no_key_means_the_browser_speaks(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = TestClient(app)
    assert c.get("/api/voice").json() == {"voice": False, "hear": False}
    assert c.post("/api/voice/speak", json={"text": "Hello"}).status_code == 503
    assert c.post("/api/voice/speak", json={"text": "  "}).status_code == 400


def test_hear_uses_the_one_transcriber(monkeypatch):
    """Speech to text has one implementation, llm.transcribe (OpenAI direct, never the scored gateway)."""
    seen = {}

    def transcribe(raw, filename, run_id=None):
        seen.update(raw=raw, filename=filename)
        return " The Hartmann flight is  late "
    monkeypatch.setattr(voice.llm, "transcribe", transcribe)
    out = TestClient(app).post("/api/voice/hear", content=b"audio", headers={"content-type": "audio/mp4"}).json()
    assert out == {"text": "The Hartmann flight is late"}
    assert seen == {"raw": b"audio", "filename": "speech.m4a"}


def test_hear_without_a_transcriber_lets_the_browser_listen(monkeypatch):
    def transcribe(raw, filename, run_id=None):
        raise RuntimeError("no OpenAI key for transcription")
    monkeypatch.setattr(voice.llm, "transcribe", transcribe)
    assert TestClient(app).post("/api/voice/hear", content=b"x", headers={"content-type": "audio/webm"}).status_code == 503


def test_the_brake_stops_a_runaway_page(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    voice._used[:] = [__import__("time").time()] * 40
    with pytest.raises(RuntimeError):
        voice.hear(b"x")
