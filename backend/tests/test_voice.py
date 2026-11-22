"""The voice desk: without a key the page falls back to the browser, with one the calls go to ElevenLabs as asked."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import voice
from app.main import app


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    voice._used.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


def test_no_key_means_the_browser_speaks():
    c = TestClient(app)
    assert c.get("/api/voice").json() == {"voice": False}
    assert c.post("/api/voice/speak", json={"text": "Hello"}).status_code == 503
    assert c.post("/api/voice/hear", content=b"abc", headers={"content-type": "audio/webm"}).status_code == 503
    assert c.post("/api/voice/speak", json={"text": "  "}).status_code == 400


def test_hear_sends_the_recording_with_the_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    seen = {}

    def post(url, headers, timeout, data, files):
        seen.update(url=url, key=headers["xi-api-key"], model=data["model_id"], file=files["file"])
        return httpx.Response(200, json={"text": " The Hartmann flight is  late ", "language_code": "eng"})
    monkeypatch.setattr(voice.httpx, "post", post)
    out = TestClient(app).post("/api/voice/hear", content=b"audio", headers={"content-type": "audio/mp4"}).json()
    assert out == {"text": "The Hartmann flight is late", "language": "eng"}
    assert seen["url"].endswith("/speech-to-text") and seen["key"] == "k" and seen["file"][0] == "speech.m4a"


def test_the_brake_stops_a_runaway_page(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    voice._used[:] = [__import__("time").time()] * 40
    with pytest.raises(RuntimeError):
        voice.hear(b"x")
