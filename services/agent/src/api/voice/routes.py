"""Voice: `/v1/audio/transcriptions` and `/v1/audio/speech` (OpenAI-compatible) and
`/v1/voice/turns`, a spoken message in and the Director's spoken reply out.

Speech itself acts for nobody, so AnythingLLM (which carries no user) may use it for its
read-aloud; a voice turn is a chat job and needs the gateway's user, as `/v1` does.
"""

import base64
import json
import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.deps import CALLER_HEADER, BrokerDep, PoolDep, SettingsDep, UserDep, user_of
from src.api.jobs import outcome
from src.api.voice import speech
from src.db.queries import facts, threads
from src.persona.layers import build_persona
from src.prompts import errors as wording
from src.queue import submit
from src.queue.models import ClientInfo, Job
from src.settings import Settings

router = APIRouter()
VOICE = ClientInfo(client="voice")


def speech_caller(request: Request) -> None:
    """A user the gateway named, or AnythingLLM; anyone else is 401."""
    if user_of(request) is None and request.headers.get(CALLER_HEADER) != "anythingllm":
        raise HTTPException(401, detail={"code": "UNKNOWN_USER", "message": wording.UNKNOWN_USER})


SpeechCaller = Annotated[None, Depends(speech_caller)]


def unavailable() -> HTTPException:
    return HTTPException(
        503, detail={"code": "SPEECH_UNAVAILABLE", "message": wording.SPEECH_UNAVAILABLE}
    )


async def read_audio(upload: UploadFile, settings: Settings) -> bytes:
    audio = await upload.read(settings.VOICE_MAX_UPLOAD_BYTES + 1)
    if len(audio) > settings.VOICE_MAX_UPLOAD_BYTES:
        limit = settings.VOICE_MAX_UPLOAD_BYTES // 1_000_000
        message = wording.AUDIO_TOO_LARGE.format(limit=limit)
        raise HTTPException(413, detail={"code": "AUDIO_TOO_LARGE", "message": message})
    return audio


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input: str = Field(min_length=1, max_length=40_000)
    voice: str | None = Field(None, pattern=r"^[a-z]{2}_[a-z]{1,20}$")


@router.post("/v1/audio/transcriptions")
async def transcriptions(
    _caller: SpeechCaller, settings: SettingsDep, file: Annotated[UploadFile, File()]
) -> dict[str, str]:
    audio = await read_audio(file, settings)
    try:
        text = await speech.transcribe(settings, audio, file.filename or "audio", file.content_type)
    except speech.SpeechUnavailable as exc:
        raise unavailable() from exc
    return {"text": text}


@router.post("/v1/audio/speech")
async def audio_speech(
    _caller: SpeechCaller, body: SpeechRequest, settings: SettingsDep
) -> Response:
    try:
        audio = await speech.speak(settings, body.input, body.voice or settings.TTS_VOICE)
    except speech.SpeechUnavailable as exc:
        raise unavailable() from exc
    return Response(audio, media_type="audio/mpeg")


async def voice_of(pool, user: str, settings: Settings) -> str:
    persona = build_persona(await facts.persona_rows(pool, user))
    return persona.identity.get("tts_voice") or settings.TTS_VOICE


def spoken(text: str) -> str:
    """A reply as read aloud: markdown marks and links dropped, the words kept."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[*_#`>|]+", "", text).strip()


def line(**fields: object) -> bytes:
    return (json.dumps(fields) + "\n").encode()


@router.post("/v1/voice/turns")
async def voice_turn(
    user: UserDep,
    broker: BrokerDep,
    pool: PoolDep,
    settings: SettingsDep,
    audio: Annotated[UploadFile, File()],
    thread_id: Annotated[str, Form(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")] = "voice",
) -> StreamingResponse:
    """NDJSON, one line per step as it happens: `transcript`, then `reply` with its `notices`,
    then `audio` (base64 mp3); or `error` with a code and message. Headers go out at once, so a
    long answer never trips the gateway's time-to-headers limit."""
    recording = await read_audio(audio, settings)

    async def steps() -> AsyncIterator[bytes]:
        try:
            said = await speech.transcribe(
                settings, recording, audio.filename or "audio", audio.content_type
            )
            if not said:
                yield line(type="error", code="AUDIO_EMPTY", message=wording.AUDIO_EMPTY)
                return
            yield line(type="transcript", text=said)
            job = Job(
                kind="chat",
                message=said,
                thread_id=thread_id,
                user=user,
                client=VOICE,
                channel="voice",
            )
            await threads.create(pool, user, job.thread_id, VOICE.client)
            await submit.submit(broker, job, settings.EVENTS_TTL_S)
            finished = await outcome(broker, job.job_id, settings.API_MAX_STREAM_S)
            if finished is None or finished["status"] != "done":
                error = (finished or {}).get("error") or {
                    "code": "JOB_ABANDONED",
                    "message": wording.JOB_ABANDONED,
                }
                yield line(type="error", **error)
                return
            result = finished.get("result", {})
            reply = result.get("reply", "")
            yield line(type="reply", text=reply, notices=result.get("notices", []))
            voice = await voice_of(pool, user, settings)
            mp3 = await speech.speak(settings, spoken(reply), voice)
            yield line(type="audio", format="mp3", data=base64.b64encode(mp3).decode())
        except speech.SpeechUnavailable:
            yield line(type="error", code="SPEECH_UNAVAILABLE", message=wording.SPEECH_UNAVAILABLE)

    return StreamingResponse(steps(), media_type="application/x-ndjson")
