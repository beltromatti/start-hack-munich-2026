"""The voice desk: a person speaks to the desk on a phone and hears its answer.

Thin over ElevenLabs with our own key (`ELEVENLABS_API_KEY`), never the 5U gateway: it is our tool, not part of a
quote. Hearing turns a recording into words (Scribe). Speaking turns the desk's checked answer into audio (Flash, the
low latency model). What the words mean is decided where it always is: `/api/ask` answers and proposes, and a
person's yes passes it to Giulia's session. No key: the page uses the browser's own voice.
"""
import os
import time

import httpx

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
    return {"voice": bool(key())}


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


def hear(audio: bytes, filename: str = "speech.webm", content_type: str = "audio/webm") -> dict:
    """A recording as words, with the language ElevenLabs heard."""
    if not audio:
        raise ValueError("no audio")
    if len(audio) > 8_000_000:
        raise ValueError("recording too long")
    if not key():
        raise RuntimeError("no ElevenLabs key")
    _brake()
    r = httpx.post(f"{API}/speech-to-text", headers={"xi-api-key": key()}, timeout=40,
                   data={"model_id": os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1"), "tag_audio_events": "false"},
                   files={"file": (filename, audio, content_type or "application/octet-stream")})
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    j = r.json()
    return {"text": " ".join(str(j.get("text") or "").split())[:600], "language": j.get("language_code")}
