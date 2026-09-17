"""The worker's queue models and keys match `contracts/` (the API's mirror is tested the same)."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from src.persona.layers import default_name
from src.queue import keys, submit
from src.queue import models as queue_models
from src.queue.models import TERMINAL, Job

CONTRACTS = Path(__file__).parents[5] / "contracts"


def load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


KEYS = load("queue_keys.v1.json")
JOBS = load("job.v1.json")
EVENTS = load("job_events.v1.json")
EVENT_TYPES = {
    cls.type: cls
    for cls in vars(queue_models).values()
    if isinstance(cls, type)
    and issubclass(cls, queue_models.Event)
    and cls is not queue_models.Event
}


def test_names():
    assert (keys.JOBS, keys.DEAD, keys.GROUP) == (
        KEYS["streams"]["jobs"],
        KEYS["streams"]["dead"],
        KEYS["group"],
    )
    assert (keys.PAYLOAD, keys.SCAN_START) == (KEYS["payload_field"], KEYS["scan_start"])
    assert submit.JOBS_MAXLEN == KEYS["jobs_maxlen"]
    assert sorted(submit.FINISHED) == sorted(KEYS["finished"])


@pytest.mark.parametrize("vector", KEYS["vectors"])
def test_key_vectors(vector):
    user, thread_id = vector["user"], vector["thread_id"]
    assert keys.job(vector["job_id"]) == vector["job"]
    assert keys.events(vector["job_id"]) == vector["events"]
    assert keys.thread(user, thread_id) == vector["thread"]
    assert keys.thread_lock(user, thread_id) == vector["thread_lock"]
    assert keys.thread_job(user, thread_id) == vector["thread_job"]
    assert keys.request(vector["digest"]) == vector["request"]


@pytest.mark.parametrize("job", JOBS["valid"])
def test_valid_jobs_round_trip(job):
    parsed = Job.model_validate(job)
    assert json.loads(parsed.model_dump_json()) == job


@pytest.mark.parametrize("case", JOBS["invalid"], ids=lambda case: case["why"])
def test_invalid_jobs_are_refused(case):
    with pytest.raises(ValidationError):
        Job.model_validate(case["job"])


def test_every_event_type_is_pinned():
    assert {event["type"] for event in EVENTS["events"]} == set(EVENT_TYPES)
    assert sorted(TERMINAL) == sorted(EVENTS["terminal"])


@pytest.mark.parametrize("event", EVENTS["events"], ids=lambda event: event["type"])
def test_events_round_trip(event):
    parsed = TypeAdapter(EVENT_TYPES[event["type"]]).validate_python(event["data"])
    assert json.loads(parsed.model_dump_json()) == event["data"]


def test_default_names_by_stage():
    names = EVENTS["defaults"]["names_by_stage"]
    assert {stage: default_name(stage) for stage in names} == names
    assert default_name("assistant") == EVENTS["defaults"]["director_name"]


def test_research_result_fields():
    from src.worker.research import RESULT_FIELDS

    assert set(EVENTS["results"]["research"]) == set(RESULT_FIELDS)


async def test_chat_result_fields():
    """The worker's chat result, produced by a run with no model output, has the pinned keys."""
    import inspect

    from src.worker import stream

    source = inspect.getsource(stream.run_chat)
    assert all(f'"{key}"' in source for key in EVENTS["results"]["chat"])


def test_status_hash_and_entry_fields():
    assert keys.STATUS_HASH_FIELDS == tuple(KEYS["status_hash_fields"])
    assert keys.STATUSES == tuple(KEYS["statuses"])
    assert (keys.ENTRY_TYPE, keys.ENTRY_DATA) == tuple(KEYS["event_entry_fields"])
