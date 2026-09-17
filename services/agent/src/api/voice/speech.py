"""The speech service (speaches): transcription and synthesis over its OpenAI-compatible API.

Its failures surface as `SpeechUnavailable`, which the routes answer as 503; nothing is guessed.
"""

import re
from collections.abc import AsyncIterator

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


# Kokoro reads a long reply best in pieces; mp3 frames join by simple concatenation.
PIECE_CHARS = 800


def pieces(text: str, limit: int = PIECE_CHARS) -> list[str]:
    """`text` split at sentence ends (or spaces, for a very long sentence) into parts of at most
    `limit` characters, in order."""
    parts: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?\n])\s+", text.strip()):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > limit:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return [part for part in parts if part]


async def speak_pieces(settings: Settings, text: str, voice: str) -> AsyncIterator[bytes]:
    """`text` read aloud, as mp3 audio for each piece as soon as it is synthesised."""
    for part in pieces(text):
        body = {
            "model": settings.TTS_MODEL,
            "voice": voice,
            "input": part,
            "response_format": "mp3",
        }
        yield (await _post(settings, "/v1/audio/speech", json=body)).content


async def speak(settings: Settings, text: str, voice: str) -> bytes:
    """`text` read aloud, as one mp3."""
    return b"".join([audio async for audio in speak_pieces(settings, text, voice)])
