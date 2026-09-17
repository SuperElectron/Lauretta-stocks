"""Voice routes with the speech service and the worker replaced by doubles."""

import base64
import json

import pytest

from src.api.voice import routes, speech
from src.queue.models import Done
from tests.unit.openai.conftest import client_for

MP3 = b"ID3fake"


@pytest.fixture
def speech_service(monkeypatch):
    calls: dict[str, list] = {"transcribe": [], "speak": []}
    heard = {"text": "how is nvidia doing"}

    async def transcribe(_settings, audio, filename, _content_type):
        calls["transcribe"].append((audio, filename))
        return heard["text"]

    async def speak(_settings, text, voice):
        calls["speak"].append((text, voice))
        return MP3

    monkeypatch.setattr(speech, "transcribe", transcribe)
    monkeypatch.setattr(speech, "speak", speak)

    async def no_facts(_pool, _user):
        return []

    monkeypatch.setattr(routes.facts, "persona_rows", no_facts)
    calls["heard"] = heard
    return calls


def audio_file(size: int = 10) -> dict:
    return {"audio": ("clip.webm", b"x" * size, "audio/webm")}


async def test_speech_needs_a_user_or_anythingllm(broker, speech_service):  # noqa: ARG001
    async with client_for(broker, user=None) as http:
        refused = await http.post("/v1/audio/speech", json={"input": "hello"})
        http.headers["X-Lauretta-Caller"] = "anythingllm"
        spoken = await http.post("/v1/audio/speech", json={"input": "hello", "voice": "tts-1"})
        allowed = await http.post("/v1/audio/speech", json={"input": "hello"})
    assert refused.status_code == 401
    assert spoken.status_code == 422
    assert allowed.status_code == 200
    assert allowed.headers["content-type"] == "audio/mpeg"
    assert allowed.content == MP3


async def test_transcription_rejects_a_recording_over_the_limit(broker, speech_service):  # noqa: ARG001
    async with client_for(broker, VOICE_MAX_UPLOAD_BYTES=5) as http:
        response = await http.post(
            "/v1/audio/transcriptions", files={"file": audio_file()["audio"]}
        )
    assert response.status_code == 413


async def test_speech_down_is_503(broker, monkeypatch):
    async def down(*_args):
        raise speech.SpeechUnavailable("x")

    monkeypatch.setattr(speech, "transcribe", down)
    async with client_for(broker) as http:
        response = await http.post(
            "/v1/audio/transcriptions", files={"file": audio_file()["audio"]}
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SPEECH_UNAVAILABLE"


@pytest.mark.usefixtures("db")
async def test_a_voice_turn_transcribes_chats_and_speaks_the_reply(broker, worker, speech_service):
    worker.reply = lambda _job, _n: [
        Done(result={"thread_id": "voice", "reply": "**Andy** says [hold](x)", "notices": []})
    ]
    async with client_for(broker, user="max") as http:
        response = await http.post("/v1/voice/turns", files=audio_file())
    steps = [json.loads(line) for line in response.text.splitlines()]
    assert [step["type"] for step in steps] == ["transcript", "reply", "audio"]
    assert steps[0]["text"] == "how is nvidia doing"
    assert steps[1]["text"] == "**Andy** says [hold](x)"
    assert base64.b64decode(steps[2]["data"]) == MP3
    assert speech_service["speak"] == [("Andy says hold", "af_heart")]
    [job] = worker.jobs
    assert (job.user, job.channel, job.client.client, job.message) == (
        "max",
        "voice",
        "voice",
        "how is nvidia doing",
    )


async def test_silence_is_reported_and_queues_nothing(broker, db, worker, speech_service):  # noqa: ARG001
    speech_service["heard"]["text"] = ""
    async with client_for(broker) as http:
        response = await http.post("/v1/voice/turns", files=audio_file())
    assert json.loads(response.text) == {
        "type": "error",
        "code": "AUDIO_EMPTY",
        "message": "no speech was heard in the recording",
    }
    assert not worker.jobs


async def test_a_voice_turn_needs_a_user(broker, speech_service):  # noqa: ARG001
    async with client_for(broker, user=None) as http:
        http.headers["X-Lauretta-Caller"] = "anythingllm"
        response = await http.post("/v1/voice/turns", files=audio_file())
    assert response.status_code == 401
