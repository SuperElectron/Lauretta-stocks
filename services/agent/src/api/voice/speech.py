"""The speech service (speaches): transcription and synthesis over its OpenAI-compatible API.

Its failures surface as `SpeechUnavailable`, which the routes answer as 503; nothing is guessed.
"""

import httpx
from loguru import logger

from src.settings import Settings

TIMEOUT_S = 120.0


class SpeechUnavailable(Exception):
    """The speech service is not configured, not reachable or answered with an error."""


def _base(settings: Settings) -> str:
    if not settings.SPEECH_URL:
        raise SpeechUnavailable("SPEECH_URL")
    return settings.SPEECH_URL.rstrip("/")


async def _post(settings: Settings, path: str, **kwargs) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as http:
            response = await http.post(_base(settings) + path, **kwargs)
    except httpx.HTTPError as exc:
        logger.bind(path=path, error=type(exc).__name__).error("speech.unreachable")
        raise SpeechUnavailable(path) from exc
    if response.status_code != 200:
        logger.bind(path=path, status=response.status_code).error("speech.failed")
        raise SpeechUnavailable(path)
    return response


async def transcribe(settings: Settings, audio: bytes, filename: str, content_type: str) -> str:
    """The text spoken in `audio`."""
    response = await _post(
        settings,
        "/v1/audio/transcriptions",
        files={"file": (filename, audio, content_type)},
        data={"model": settings.STT_MODEL},
    )
    return str(response.json().get("text", "")).strip()


async def speak(settings: Settings, text: str, voice: str) -> bytes:
    """`text` read aloud, as mp3."""
    body = {"model": settings.TTS_MODEL, "voice": voice, "input": text, "response_format": "mp3"}
    response = await _post(settings, "/v1/audio/speech", json=body)
    return response.content
