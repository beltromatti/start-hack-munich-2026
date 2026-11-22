"""The voice desk: a person speaks to the desk on a phone and hears its answer.

Never the 5U gateway: it is our tool, not part of a quote. Speaking turns the desk's checked answer into audio with
ElevenLabs (Flash, the low latency model, our own `ELEVENLABS_API_KEY`). Hearing uses the one transcriber we already
have, `llm.transcribe` (OpenAI direct, the same call that reads customers' voice messages), so there is one
implementation of speech to text. What the words mean is decided where it always is: `/api/ask` answers and
proposes, and a person's yes passes it to Giulia's session. A missing key: the page uses the browser's own voice.
"""
import os
import time

import httpx

from . import llm

API = "https://api.elevenlabs.io/v1"
# Alice: a clear, calm British voice. Any other voice from the ElevenLabs library through ELEVENLABS_VOICE_ID.
VOICE = "Xb7hH8MSUJpSbSDYk0k2"
_used: list[float] = []  # a brake on a runaway page (40 calls a minute), so a loop cannot burn the credits


def key() -> str:
    return os.getenv("ELEVENLABS_API_KEY", "").strip()


def _brake() -> None:
    now = time.time()
    _used[:] = [t for t in _used if now - t < 60]
    if len(_used) >= 40:
        raise RuntimeError("too many voice calls for a minute")
    _used.append(now)


def status() -> dict:
    return {"voice": bool(key()), "hear": bool(os.getenv("OPENAI_API_KEY", "").strip())}


def speak(text: str):
    """The answer as mp3, streamed as ElevenLabs makes it, so the first word plays before the last is made."""
    text = " ".join(str(text or "").split())[:700]
    if not text:
        raise ValueError("nothing to say")
    if not key():
        raise RuntimeError("no ElevenLabs key")
    _brake()
    voice = os.getenv("ELEVENLABS_VOICE_ID", VOICE)
    client = httpx.Client(timeout=30)
    req = client.build_request(
        "POST", f"{API}/text-to-speech/{voice}/stream", params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key()},
        json={"text": text, "model_id": os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}})
    res = client.send(req, stream=True)
    if res.status_code >= 400:
        detail = res.read()[:200]
        res.close()
        client.close()
        raise RuntimeError(f"ElevenLabs {res.status_code}: {detail!r}")

    def chunks():
        try:
            yield from res.iter_bytes()
        finally:
            res.close()
            client.close()
    return chunks()


def hear(audio: bytes, filename: str = "speech.webm") -> dict:
    """A recording as words, through the project's one transcriber (`llm.transcribe`, never the gateway)."""
    if not audio:
        raise ValueError("no audio")
    if len(audio) > 8_000_000:
        raise ValueError("recording too long")
    _brake()
    return {"text": " ".join(llm.transcribe(audio, filename).split())[:600]}
