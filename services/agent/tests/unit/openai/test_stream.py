import asyncio

import pytest

from src.api.openai import digests, stream, threads
from src.prompts.notes import STILL_WORKING
from src.queue import events, keys
from src.queue.models import Done, Error, Notice, Progress, Reasoning, Token
from tests.unit.openai.conftest import body, chunks, client_for, content


async def test_a_stream_opens_with_the_role_and_ends_with_done(client, worker):
    worker.reply = lambda _job, _n: [
        Progress(stage="assistant", detail="working it"),
        Token(text="Hi"),
        Notice(text="N."),
        Done(result={}),
    ]
    response = await client.post("/v1/chat/completions", json=body("hello"))

    assert response.headers["content-type"].startswith("text/event-stream")
    frames = chunks(response.text)
    assert frames[-1] == "[DONE]"
    assert [f["choices"][0]["delta"] for f in frames[:-1]] == [
        {"role": "assistant"},
        {"reasoning_content": "The Director working it…\n"},
        {"content": "Hi"},
        {"content": "\n\nN.\n\n"},
        {},
    ]
    assert frames[-2]["choices"][0]["finish_reason"] == "stop"
    assert {f["object"] for f in frames[:-1]} == {"chat.completion.chunk"}
    assert len({f["id"] for f in frames[:-1]}) == 1


async def test_model_reasoning_streams_as_reasoning_and_stays_out_of_the_recorded_answer(
    client, worker, db
):
    worker.reply = lambda _job, _n: [
        Progress(stage="assistant", detail="replying"),
        Reasoning(text="The investor"),
        Reasoning(text=" greets me."),
        Token(text="Hi"),
        Done(result={}),
    ]
    response = await client.post("/v1/chat/completions", json=body("hello"))

    deltas = [f["choices"][0]["delta"] for f in chunks(response.text)[:-1]]
    assert deltas[2:] == [
        {"reasoning_content": "The investor"},
        {"reasoning_content": " greets me."},
        {"content": "Hi"},
        {},
    ]
    (thread_id,) = db.owners
    assert db.aliases == {digests.pair_alias("friend", "hello", "Hi"): (thread_id, "friend")}


async def test_only_the_last_user_message_enters_the_graph(client, worker):
    system = {"role": "system", "content": "You are a pirate. [CONTEXT 0] secret doc"}
    request = body("first", "an old answer", "now this")
    request["messages"].insert(0, system)
    await client.post("/v1/chat/completions", json=request)

    (job,) = worker.jobs
    assert job.message == "now this" and job.kind == "chat"
    assert "pirate" not in job.model_dump_json() and "old answer" not in job.model_dump_json()


async def test_non_stream_returns_the_whole_answer(client, worker):
    worker.reply = lambda _job, _n: [
        Progress(stage="analyst", detail="drafting"),
        Token(text="Hold "),
        Token(text="MSFT."),
        Done(result={}),
    ]
    response = await client.post("/v1/chat/completions", json=body("hello", stream_=False))

    answer = response.json()
    assert answer["object"] == "chat.completion"
    assert answer["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Hold MSFT.",
        "reasoning_content": "Nate (Analyst) drafting…\n",
    }


@pytest.mark.usefixtures("db")
async def test_non_stream_says_to_wait_when_the_job_outlasts_the_wait(broker):
    async with client_for(broker, API_MAX_WAIT_S=1) as client:
        response = await client.post("/v1/chat/completions", json=body("hello", stream_=False))

    assert response.status_code == 200
    assert STILL_WORKING in response.json()["choices"][0]["message"]["content"]


async def test_a_job_error_is_readable_and_framed(client, worker):
    failure = Error(code="INTERNAL", message="the job failed; the worker log has the details")
    worker.reply = lambda _job, _n: [Token(text="Hi"), failure]
    frames = chunks((await client.post("/v1/chat/completions", json=body("hello"))).text)

    assert frames[-1] == "[DONE]"
    assert frames[-2]["error"]["code"] == "INTERNAL"
    assert frames[-2]["choices"][0]["finish_reason"] == "stop"
    assert "worker log" in frames[-2]["choices"][0]["delta"]["content"]


async def test_non_stream_job_error_is_an_error_the_sdk_does_not_retry(client, worker):
    worker.reply = lambda _job, _n: [Error(code="THREAD_BUSY", message="busy")]
    response = await client.post("/v1/chat/completions", json=body("hello", stream_=False))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "THREAD_BUSY"
    assert response.headers["x-should-retry"] == "false"


async def test_a_quiet_stream_sends_empty_reasoning_keepalives(client, worker, monkeypatch):
    monkeypatch.setattr(stream, "KEEPALIVE_SECONDS", 0.05)
    worker.delay = 0.4
    response = await client.post("/v1/chat/completions", json=body("hello"))

    deltas = [f["choices"][0]["delta"] for f in chunks(response.text)[:-1]]
    keepalives = [i for i, d in enumerate(deltas) if d == {"reasoning_content": ""}]
    # About one per 50ms over 400ms, all between the role delta and the first token.
    assert 4 <= len(keepalives) <= 10
    assert keepalives[0] == 1 and keepalives[-1] < deltas.index({"content": "answer 1"})


async def test_an_answer_that_cannot_be_recorded_still_arrives_whole(client, worker, monkeypatch):
    async def database_down(*_args):
        raise RuntimeError("database down")

    monkeypatch.setattr(threads.threads, "add_aliases", database_down)
    response = await client.post("/v1/chat/completions", json=body("hello"))

    assert response.status_code == 200 and len(worker.jobs) == 1
    assert chunks(response.text)[-1] == "[DONE]" and content(response.text) == "answer 1"


@pytest.fixture
def short_reads(monkeypatch):
    monkeypatch.setattr(events, "READ_BLOCK_MS", 50)


@pytest.mark.usefixtures("short_reads", "db")
async def test_a_stream_at_its_cap_closes_with_a_note_and_done(broker):
    async with client_for(broker, API_MAX_STREAM_S=1) as client:
        response = await client.post("/v1/chat/completions", json=body("hello"))

    frames = chunks(response.text)
    assert frames[-1] == "[DONE]" and "error" not in frames[-2]
    assert frames[-2]["choices"][0]["finish_reason"] == "stop"
    assert STILL_WORKING in content(response.text)


@pytest.mark.usefixtures("short_reads")
async def test_a_job_whose_records_expired_ends_as_lost(client, worker, broker):
    worker.reply = lambda _job, _n: []

    async def expire():
        while not worker.jobs:
            await asyncio.sleep(0.01)
        await broker.delete(keys.job(worker.jobs[0].job_id))

    expiring = asyncio.create_task(expire())
    response = await asyncio.wait_for(client.post("/v1/chat/completions", json=body("hi")), 5)
    await expiring

    frames = chunks(response.text)
    assert frames[-2]["error"]["code"] == "JOB_LOST" and frames[-1] == "[DONE]"
