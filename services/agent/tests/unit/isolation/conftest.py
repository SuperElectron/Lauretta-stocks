"""Isolation tests' fixtures: a fake broker, the threads table in memory, a worker double, and
two investors' data behind the query functions (`two_users.py`)."""

import asyncio

import pytest
from fakeredis import FakeAsyncRedis

from src.api.openai import threads
from src.queue import keys
from src.queue.models import Job
from tests.unit.isolation.two_users import two_users  # noqa: F401
from tests.unit.openai.conftest import FakeThreads, FakeWorker


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def db(monkeypatch) -> FakeThreads:
    """The threads table in memory, for the OpenAI adapter and `POST /v1/jobs` alike."""
    fake = FakeThreads()
    for name in ("create", "find_aliases", "add_aliases"):
        monkeypatch.setattr(threads.threads, name, getattr(fake, name))
    return fake


@pytest.fixture
async def worker(broker):
    fake = FakeWorker(broker)
    task = asyncio.create_task(fake.run())
    yield fake
    task.cancel()


async def queued(broker) -> list[Job]:
    found = await broker.xread({keys.JOBS: "0-0"})
    entries = found[0][1] if found else []
    return [Job.model_validate_json(fields[keys.PAYLOAD]) for _, fields in entries]
