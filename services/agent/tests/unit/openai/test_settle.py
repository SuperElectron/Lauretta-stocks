"""A chat app hangs up at `finish_reason`; the answer is recorded all the same."""

import asyncio
import json

import pytest

from src.api.app import create_app
from src.api.openai import digests, settle, threads
from src.api.openai.models import ChatRequest
from src.queue import keys
from tests.unit.openai.conftest import body, client_for
from tests.utils import settings


async def hang_up_at_finish(app, request: dict) -> list[bytes]:
    """Drives the app as uvicorn does (ASGI spec 2.3), for a client like openai-node under
    AnythingLLM: it disconnects once the chunk with `finish_reason` arrives, before `[DONE]`.
    Starlette then cancels the response body mid-stream."""
    received: list[bytes] = []
    finished, asked = asyncio.Event(), False
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions", "query_string": b"", "root_path": "",
        "headers": [
            (b"host", b"api"), (b"content-type", b"application/json"), (b"x-lauretta-user", b"mat"),
        ],
        "client": ("127.0.0.1", 50000), "server": ("api", 80),
    }  # fmt: skip

    async def receive() -> dict:
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": json.dumps(request).encode()}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        chunk = message.get("body", b"")
        received.append(chunk)
        if b'"finish_reason": "stop"' in chunk:
            finished.set()
            # The client is gone: nothing more is ever written.
            await asyncio.Event().wait()

    await asyncio.wait_for(app(scope, receive, send), 5)
    return received


@pytest.mark.usefixtures("worker")
async def test_hanging_up_at_finish_still_releases_the_request_and_records_the_alias(broker, db):
    app = create_app(with_lifespan=False)
    app.state.settings, app.state.broker, app.state.pool = settings(), broker, None
    request = body("hello")
    key = keys.request(digests.request_key("mat", ChatRequest.model_validate(request), None))

    received = await hang_up_at_finish(app, request)
    await asyncio.gather(*settle.running)

    assert any(b'"finish_reason": "stop"' in chunk for chunk in received)
    assert not any(b"[DONE]" in chunk for chunk in received)
    assert await broker.exists(key) == 0
    ((_, thread_id),) = db.threads
    assert db.aliases == {("mat", digests.pair_alias("mat", "hello", "answer 1")): thread_id}


async def test_a_failed_record_is_logged_with_the_job_id(monkeypatch):
    logged: list[tuple[str, str]] = []

    class Log:
        def __init__(self, job_id: str) -> None:
            self.job_id = job_id

        def opt(self, **_kwargs):
            return self

        def error(self, event: str) -> None:
            logged.append((self.job_id, event))

    monkeypatch.setattr(settle.logger, "bind", lambda job_id: Log(job_id))

    async def database_down(_text, _done):
        raise RuntimeError("database down")

    settle.start("job-1", database_down, "answer", True)
    await asyncio.gather(*settle.running, return_exceptions=True)
    await asyncio.sleep(0)

    assert logged == [("job-1", "openai.answer_not_recorded")]
    assert not settle.running


@pytest.mark.usefixtures("worker")
@pytest.mark.parametrize("stream_", [True, False])
async def test_a_client_that_reads_to_the_end_finds_the_answer_recorded(
    broker, db, monkeypatch, stream_
):
    slow_add = db.add_aliases

    async def slow_database(*args):
        await asyncio.sleep(0.1)
        await slow_add(*args)

    monkeypatch.setattr(threads.threads, "add_aliases", slow_database)
    async with client_for(broker) as client:
        await client.post("/v1/chat/completions", json=body("hello", stream_=stream_))

        assert ("mat", digests.pair_alias("mat", "hello", "answer 1")) in db.aliases


async def test_finish_stops_waiting_after_the_timeout_and_logs_the_job(monkeypatch):
    logged = []

    class Log:
        def __init__(self, job_id):
            self.job_id = job_id

        def error(self, event):
            logged.append((self.job_id, event))

    monkeypatch.setattr(settle.logger, "bind", lambda job_id: Log(job_id))
    release = asyncio.Event()

    async def stalled(_text, _done):
        await release.wait()

    task = settle.start("job-2", stalled, "answer", True)
    await asyncio.wait_for(settle.finish([task], timeout=0.01), timeout=1)
    assert logged == [("job-2", "openai.answer_recording_slow")]
    assert not task.done()
    release.set()
    await task
