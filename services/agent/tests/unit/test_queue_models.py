import pytest
from pydantic import ValidationError

from src.queue.models import Done, Error, Job, JobRequest, Reset, Token
from tests.utils import settings


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "chat"},
        {"kind": "chat", "message": ""},
        {"kind": "chat", "message": "hi", "ticker": "MSFT"},
        {"kind": "research"},
        {"kind": "research", "ticker": "MSFT", "message": "hi"},
        {"kind": "research", "ticker": "MSFT; DROP"},
        {"kind": "chat", "message": "hi", "thread_id": "has spaces"},
        {"kind": "chat", "message": "hi", "callback_url": "https://example.com/hook"},
        {"kind": "chat", "message": "hi", "unexpected": 1},
        {"kind": "trade", "ticker": "MSFT"},
    ],
)
def test_invalid_requests_are_refused(body):
    with pytest.raises(ValidationError):
        JobRequest.model_validate(body)


def test_valid_requests_default_the_thread():
    chat = JobRequest.model_validate({"kind": "chat", "message": "hi"})
    research = JobRequest.model_validate({"kind": "research", "ticker": "BRK-B"})
    assert chat.thread_id == "main" and research.ticker == "BRK-B"


def test_a_job_round_trips_through_its_json():
    job = Job(user="mat", kind="chat", message="hi", client={"client": "ios"})
    assert Job.model_validate_json(job.model_dump_json()) == job


def test_events_serialize_their_fields_and_name_their_type():
    assert (Token(text="Hel").type, Token(text="Hel").model_dump_json()) == (
        "token",
        '{"text":"Hel"}',
    )
    assert Reset().model_dump_json() == "{}"
    assert Done(result={"reply": "ok"}).model_dump_json() == '{"result":{"reply":"ok"}}'
    assert Error(code="X", message="y").type == "error"


def test_lock_wait_must_end_before_a_job_counts_as_abandoned():
    with pytest.raises(ValidationError, match="AGENT_LOCK_WAIT_MS"):
        settings(AGENT_LOCK_WAIT_MS=60_000, BROKER_MIN_IDLE_MS=60_000)
    assert settings(AGENT_LOCK_WAIT_MS=1_000, BROKER_MIN_IDLE_MS=60_000)


def test_the_cli_needs_no_broker_settings():
    assert settings(BROKER_URL=None).BROKER_URL is None
    with pytest.raises(ValueError, match="BROKER_URL"):
        settings(BROKER_URL=None).broker_url()


def test_wait_stays_under_the_gateway_timeout_by_default():
    assert settings().API_MAX_WAIT_S == 25
    assert settings().API_MAX_STREAM_S == 900
