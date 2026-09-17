"""An API with a fake broker, an in-memory threads table and a worker double."""

import asyncio
import contextlib
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from src.api.app import create_app
from src.api.openai import threads
from src.queue import events, keys, submit
from src.queue.models import Done, Event, Job, Token
from tests.utils import settings


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


class FakeThreads:
    """`src.db.queries.threads`, in memory."""

    def __init__(self) -> None:
        self.owners: dict[str, str] = {}
        self.aliases: dict[str, tuple[str, str]] = {}

    async def create(self, _pool, thread_id, user_id, _client):
        if thread_id in self.owners:
            return False
        self.owners[thread_id] = user_id
        return True

    async def owner(self, _pool, thread_id):
        return self.owners.get(thread_id)

    async def find_aliases(self, _pool, user_id, alias_hashes):
        found = {alias: self.aliases.get(alias, (None, None)) for alias in alias_hashes}
        return {alias: thread for alias, (thread, owner) in found.items() if owner == user_id}

    async def add_aliases(self, _pool, user_id, thread_id, alias_hashes):
        for alias in alias_hashes:
            self.aliases.setdefault(alias, (thread_id, user_id))


@pytest.fixture
def db(monkeypatch) -> FakeThreads:
    fake = FakeThreads()
    for name in ("create", "owner", "find_aliases", "add_aliases"):
        monkeypatch.setattr(threads.threads, name, getattr(fake, name))
    return fake


@contextlib.asynccontextmanager
async def client_for(broker, **overrides):
    app = create_app(with_lifespan=False)
    app.state.settings = settings(**{"API_MAX_WAIT_S": 5, **overrides})
    app.state.broker, app.state.pool = broker, None
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as http:
        yield http


@pytest.fixture
async def client(broker, db):  # noqa: ARG001
    async with client_for(broker) as http:
        yield http


class FakeWorker:
    """Answers each queued job in turn with `reply(job, n)`, marking its status as a worker
    would. `reply` returning nothing leaves the job queued."""

    def __init__(self, broker) -> None:
        self.broker = broker
        self.jobs: list[Job] = []
        self.delay = 0.0
        self.reply: Callable[[Job, int], list[Event]] = lambda _job, n: [
            Token(text=f"answer {n}"),
            Done(result={}),
        ]

    async def run(self) -> None:
        after = "0-0"
        while True:
            for _stream, entries in await self.broker.xread({keys.JOBS: after}):
                for entry_id, fields in entries:
                    after = entry_id
                    job = Job.model_validate_json(fields[keys.PAYLOAD])
                    self.jobs.append(job)
                    await asyncio.sleep(self.delay)
                    await self.answer(job, self.reply(job, len(self.jobs)))
            await asyncio.sleep(0.005)

    async def answer(self, job: Job, outcome: list[Event]) -> None:
        for event in outcome:
            await events.publish(self.broker, job.job_id, event, 60)
            if event.type in ("done", "error"):
                status = "done" if event.type == "done" else "failed"
                await submit.mark(self.broker, job.job_id, 60, status=status)


@pytest.fixture
async def worker(broker):
    fake = FakeWorker(broker)
    task = asyncio.create_task(fake.run())
    yield fake
    task.cancel()


def body(*texts: str, stream_: bool = True, **extra: Any) -> dict[str, Any]:
    """A request whose messages alternate user and assistant, starting with the user."""
    roles = ["user", "assistant"]
    messages = [{"role": roles[i % 2], "content": t} for i, t in enumerate(texts)]
    return {"model": "lauretta", "messages": messages, "stream": stream_, **extra}


def chunks(text: str) -> list[Any]:
    frames = text.strip().split("\n\n")
    assert all(f.startswith("data: ") for f in frames)
    return [f[6:] if f == "data: [DONE]" else json.loads(f[6:]) for f in frames]


def content(text: str) -> str:
    return "".join(
        f["choices"][0]["delta"].get("content", "") for f in chunks(text) if isinstance(f, dict)
    )
