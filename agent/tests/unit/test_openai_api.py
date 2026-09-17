import asyncio
import contextlib
import json

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from src.api.app import create_app
from src.api.openai import stream, threads
from src.api.openai.models import ChatRequest
from src.queue import events, keys
from src.queue.models import Done, Error, Job, Notice, Progress, Token
from tests.utils import settings


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def owners(monkeypatch):
    """The threads table, in memory."""
    table: dict[str, str] = {}

    async def claim(_pool, thread_id, user_id, _client):
        return table.setdefault(thread_id, user_id)

    monkeypatch.setattr(threads.threads, "claim", claim)
    return table


@contextlib.asynccontextmanager
async def client_for(broker, **overrides):
    app = create_app(with_lifespan=False)
    app.state.settings = settings(**{"API_MAX_WAIT_S": 5, **overrides})
    app.state.broker, app.state.pool = broker, None
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as http:
        yield http


@pytest.fixture
async def client(broker, owners):  # noqa: ARG001
    async with client_for(broker) as http:
        yield http


def body(*texts: str, stream_: bool = True, **extra) -> dict:
    roles = ["user", "assistant"]
    messages = [{"role": roles[i % 2], "content": t} for i, t in enumerate(texts)]
    return {"model": "lauretta", "messages": messages, "stream": stream_, **extra}


async def queued_jobs(broker) -> list[Job]:
    response = await broker.xread({keys.JOBS: "0-0"})
    return [
        Job.model_validate_json(f[keys.PAYLOAD]) for _s, entries in response for _i, f in entries
    ]


async def work(broker, *outcome, delay: float = 0.0) -> None:
    """A worker double: publishes `outcome` for the first queued job."""
    while not await broker.exists(keys.JOBS):
        await asyncio.sleep(0.01)
    (job, *_) = await queued_jobs(broker)
    await asyncio.sleep(delay)
    for event in outcome:
        await events.publish(broker, job.job_id, event, 60)


def chunks(text: str) -> list[dict | str]:
    frames = text.strip().split("\n\n")
    assert all(f.startswith("data: ") for f in frames)
    return [f[6:] if f == "data: [DONE]" else json.loads(f[6:]) for f in frames]


async def test_models_lists_the_director(client):
    response = await client.get("/v1/models")
    assert [m["id"] for m in response.json()["data"]] == ["lauretta"]


async def test_a_stream_opens_with_the_role_and_ends_with_done(client, broker):
    working = asyncio.create_task(
        work(
            broker,
            Progress(stage="assistant", detail="replying"),
            Token(text="Hi"),
            Notice(text="N."),
            Done(result={}),
        )
    )
    response = await client.post("/v1/chat/completions", json=body("hello"))
    await working

    assert response.headers["content-type"].startswith("text/event-stream")
    frames = chunks(response.text)
    assert frames[-1] == "[DONE]"
    deltas = [f["choices"][0]["delta"] for f in frames[:-1]]
    assert deltas == [
        {"role": "assistant"},
        {"reasoning_content": "The Director replying…\n"},
        {"content": "Hi"},
        {"content": "\n\nN.\n\n"},
        {},
    ]
    assert frames[-2]["choices"][0]["finish_reason"] == "stop"
    assert {f["object"] for f in frames[:-1]} == {"chat.completion.chunk"}
    assert len({f["id"] for f in frames[:-1]}) == 1


async def test_only_the_last_user_message_enters_the_graph(client, broker):
    messages = [
        {"role": "system", "content": "You are a pirate. [CONTEXT 0] secret doc"},
        *body("first", "an old answer", "now this")["messages"],
    ]
    working = asyncio.create_task(work(broker, Done(result={})))
    await client.post("/v1/chat/completions", json={"model": "lauretta", "messages": messages})
    await working

    (job,) = await queued_jobs(broker)
    assert job.message == "now this" and job.kind == "chat"
    assert "pirate" not in job.model_dump_json() and "old answer" not in job.model_dump_json()


def test_the_thread_follows_the_first_message_or_the_header():
    turn1 = ChatRequest.model_validate(body("hello"))
    turn2 = ChatRequest.model_validate(body("hello", "hi there", "what about MSFT?"))
    other = ChatRequest.model_validate(body("goodbye"))

    key = threads.thread_id_for
    assert key("friend", turn1, None) == key("friend", turn2, None)
    assert key("friend", turn1, None) != key("friend", other, None)
    assert key("friend", turn1, None) != key("someone", turn1, None)
    assert key("friend", turn1, "phone") == key("friend", other, "phone")
    assert key("friend", turn1, "phone") != key("someone", turn1, "phone")
    assert key("friend", turn1, None).startswith("oa-") and len(key("friend", turn1, None)) == 35


def test_the_same_words_as_a_new_turn_are_a_new_job():
    once = ChatRequest.model_validate(body("yes"))
    again = ChatRequest.model_validate(body("yes", "ok", "yes"))
    assert threads.job_id_for("friend", "t", once) == threads.job_id_for("friend", "t", once)
    assert threads.job_id_for("friend", "t", once) != threads.job_id_for("friend", "t", again)


async def test_a_retried_request_attaches_to_the_same_job(client, broker):
    working = asyncio.create_task(work(broker, Token(text="Hi"), Done(result={})))
    first = await client.post("/v1/chat/completions", json=body("hello"))
    await working
    second = await client.post("/v1/chat/completions", json=body("hello"))

    assert len(await queued_jobs(broker)) == 1
    assert chunks(first.text) == chunks(second.text)
    assert "Hi" in second.text


async def test_identical_requests_at_once_start_one_job(client, broker):
    working = asyncio.create_task(work(broker, Token(text="Hi"), Done(result={}), delay=0.1))
    both = await asyncio.gather(
        *(client.post("/v1/chat/completions", json=body("hello")) for _ in range(2))
    )
    await working

    assert len(await queued_jobs(broker)) == 1
    assert all("Hi" in response.text for response in both)


async def test_non_stream_returns_the_whole_answer(client, broker):
    working = asyncio.create_task(
        work(
            broker,
            Progress(stage="analyst", detail="drafting"),
            Token(text="Hold "),
            Token(text="MSFT."),
            Done(result={}),
        )
    )
    response = await client.post("/v1/chat/completions", json=body("hello", stream_=False))
    await working

    answer = response.json()
    assert answer["object"] == "chat.completion"
    assert answer["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Hold MSFT.",
        "reasoning_content": "The Royal Analyst drafting…\n",
    }
    assert answer["usage"]["total_tokens"] == 0


async def test_non_stream_says_to_ask_again_when_the_job_outlasts_the_wait(broker, owners):  # noqa: ARG001
    async with client_for(broker, API_MAX_WAIT_S=1) as client:
        response = await client.post("/v1/chat/completions", json=body("hello", stream_=False))

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == stream.STILL_WORKING


async def test_a_job_error_is_readable_and_framed(client, broker):
    failure = Error(code="INTERNAL", message="the job failed; the worker log has the details")
    working = asyncio.create_task(work(broker, Token(text="Hi"), failure))
    response = await client.post("/v1/chat/completions", json=body("hello"))
    await working

    frames = chunks(response.text)
    assert frames[-1] == "[DONE]"
    last = frames[-2]
    assert last["error"]["code"] == "INTERNAL"
    assert last["choices"][0]["finish_reason"] == "stop"
    assert "worker log" in last["choices"][0]["delta"]["content"]


async def test_non_stream_job_error_is_an_openai_error(client, broker):
    working = asyncio.create_task(work(broker, Error(code="THREAD_BUSY", message="busy")))
    response = await client.post("/v1/chat/completions", json=body("hello", stream_=False))
    await working

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "THREAD_BUSY"


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (body("hello", model="gpt-4o"), 404, "model_not_found"),
        ({"model": "lauretta", "messages": []}, 400, "invalid_request"),
        (
            {"model": "lauretta", "messages": [{"role": "user", "content": 7}]},
            400,
            "invalid_request",
        ),
        (body("hello", "an answer"), 400, "invalid_last_message"),
        (body("x" * 20_001), 400, "message_too_long"),
    ],
)
async def test_bad_requests_are_openai_errors_and_queue_nothing(
    client, broker, payload, status, code
):
    response = await client.post("/v1/chat/completions", json=payload)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert await broker.exists(keys.JOBS) == 0


async def test_errors_never_echo_input_or_leak_internals(client, broker, monkeypatch):
    secret = "sk-live-do-not-echo"
    bad = await client.post(
        "/v1/chat/completions",
        json={"model": "lauretta", "messages": [{"role": "user", "content": {"k": secret}}]},
    )
    assert bad.status_code == 400 and secret not in bad.text
    not_json = await client.post("/v1/chat/completions", content=b"{" + secret.encode())
    assert not_json.status_code == 400 and secret not in not_json.text

    async def database_down(*_args):
        raise RuntimeError("postgresql://lauretta:hunter2@db/lauretta refused")

    monkeypatch.setattr(threads.threads, "claim", database_down)
    down = await client.post("/v1/chat/completions", json=body("hello"))
    assert down.status_code == 500
    assert "hunter2" not in down.text and "Traceback" not in down.text
    assert await broker.exists(keys.JOBS) == 0


async def test_a_thread_started_by_someone_else_is_not_found(client, broker, owners):
    request = ChatRequest.model_validate(body("hello"))
    owners[threads.thread_id_for("friend", request, None)] = "someone-else"

    response = await client.post("/v1/chat/completions", json=body("hello"))

    assert (response.status_code, response.json()["error"]["code"]) == (404, "thread_not_found")
    assert await broker.exists(keys.JOBS) == 0


async def test_a_bad_thread_header_is_refused(client):
    response = await client.post(
        "/v1/chat/completions", json=body("hello"), headers={"X-Thread-Id": "no spaces"}
    )
    assert response.json()["error"]["code"] == "invalid_thread_id"


async def test_a_quiet_stream_sends_empty_reasoning_keepalives(client, broker, monkeypatch):
    monkeypatch.setattr(stream, "KEEPALIVE_SECONDS", 0.05)
    working = asyncio.create_task(work(broker, Token(text="Hi"), Done(result={}), delay=0.4))
    response = await client.post("/v1/chat/completions", json=body("hello"))
    await working

    deltas = [f["choices"][0]["delta"] for f in chunks(response.text)[:-1]]
    keepalives = [i for i, d in enumerate(deltas) if d == {"reasoning_content": ""}]
    # About one per 50ms over 400ms, all between the role delta and the first token.
    assert 4 <= len(keepalives) <= 10
    assert keepalives[0] == 1 and keepalives[-1] < deltas.index({"content": "Hi"})


@pytest.fixture
def short_reads(monkeypatch):
    monkeypatch.setattr(events, "READ_BLOCK_MS", 50)


@pytest.mark.usefixtures("short_reads", "owners")
async def test_a_stream_at_its_cap_closes_with_a_note_and_done(broker):
    async with client_for(broker, API_MAX_STREAM_S=1) as client:
        response = await client.post("/v1/chat/completions", json=body("hello"))

    frames = chunks(response.text)
    assert frames[-1] == "[DONE]"
    assert frames[-2]["choices"][0]["finish_reason"] == "stop"
    assert "still at work" in frames[-2]["choices"][0]["delta"]["content"]
    assert "error" not in frames[-2]


@pytest.mark.usefixtures("short_reads")
async def test_a_job_whose_records_expired_ends_as_lost(client, broker):
    async def expire():
        while not await broker.exists(keys.JOBS):
            await asyncio.sleep(0.01)
        (job,) = await queued_jobs(broker)
        await broker.delete(keys.job(job.job_id))

    expiring = asyncio.create_task(expire())
    response = await asyncio.wait_for(client.post("/v1/chat/completions", json=body("hi")), 5)
    await expiring

    frames = chunks(response.text)
    assert frames[-2]["error"]["code"] == "JOB_LOST" and frames[-1] == "[DONE]"
