import json

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from src.app import App
from src.errors import ReplyTruncated
from src.queue import keys
from src.queue.lock import ThreadLock
from src.queue.models import ClientInfo, Job
from src.worker import callback
from src.worker.handler import INTERNAL, JobHandler
from tests.utils import settings

SECRET = "sk-ant-api03-secret at /Users/someone/.env"


def chat_graph(node):
    graph = StateGraph(MessagesState)
    graph.add_node("agent", node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=InMemorySaver())


async def replies(_state):
    return {"messages": [AIMessage(content="Hello")]}


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


def handler_for(broker, node=replies, signals=None, **overrides):
    async def record_signals(values, source):
        if signals is not None:
            signals.append((values, source))

    app = App(chat=chat_graph(node), research=None, pipeline=None, record_signals=record_signals)
    return JobHandler(app, broker, settings(AGENT_LOCK_WAIT_MS=100, **overrides))


async def events_of(broker, job_id):
    return [(f["type"], json.loads(f["data"])) for _, f in await broker.xrange(keys.events(job_id))]


async def test_a_chat_job_publishes_done_records_signals_and_status(broker):
    signals = []
    job = Job(kind="chat", message="hi", client=ClientInfo(ip="100.64.0.7", client="phone"))
    await handler_for(broker, signals=signals).run(job)

    assert (await events_of(broker, job.job_id))[-1] == (
        "done",
        {"result": {"thread_id": "main", "reply": "Hello", "notices": []}},
    )
    assert signals == [({"ip": "100.64.0.7", "client": "phone", "channel": "api"}, "gateway")]
    status = await broker.hgetall(keys.job(job.job_id))
    assert status["status"] == "done" and "finished_at" in status
    assert await broker.ttl(keys.events(job.job_id)) > 0


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError(SECRET), {"code": "INTERNAL", "message": INTERNAL.message}),
        (ReplyTruncated(), {"code": "REPLY_TRUNCATED", "message": ReplyTruncated.message}),
    ],
)
async def test_errors_carry_a_code_and_never_the_internals(broker, error, expected):
    async def fails(_state):
        raise error

    job = Job(kind="chat", message="hi")
    await handler_for(broker, fails).run(job)

    published = await events_of(broker, job.job_id)
    assert published[-1] == ("error", expected)
    assert SECRET not in json.dumps(published)
    assert await broker.hget(keys.job(job.job_id), "error_code") == expected["code"]


async def test_a_busy_thread_fails_the_job_thread_busy(broker):
    await ThreadLock(broker, "main", 10_000, 100).acquire()
    job = Job(kind="chat", message="hi")
    await handler_for(broker).run(job)
    assert (await events_of(broker, job.job_id))[-1][1]["code"] == "THREAD_BUSY"


async def test_a_finished_job_delivered_again_is_not_run_again(broker):
    job = Job(kind="chat", message="hi")
    handler = handler_for(broker)
    await handler.run(job)
    await handler.run(job)
    assert [kind for kind, _ in await events_of(broker, job.job_id)] == ["done"]


async def test_a_redelivered_unfinished_job_resets_what_it_streamed(broker):
    job = Job(kind="chat", message="hi")
    handler = handler_for(broker)
    await broker.xadd(keys.events(job.job_id), {"type": "token", "data": '{"text":"Hal"}'})
    await handler.run(job)
    assert [kind for kind, _ in await events_of(broker, job.job_id)] == ["token", "reset", "done"]


async def test_a_dead_job_tells_the_client(broker):
    job = Job(kind="chat", message="hi")
    await handler_for(broker).dead(job, "not finished in 3 deliveries")
    assert (await events_of(broker, job.job_id)) == [
        ("error", {"code": "JOB_ABANDONED", "message": "the job did not finish"})
    ]


async def test_a_failed_callback_is_recorded_on_the_job_not_retried(broker, monkeypatch):
    posts = []

    async def deliver(url, body, _timeout_s):
        posts.append((url, body))
        return "HTTP 500"

    monkeypatch.setattr(callback, "deliver", deliver)
    job = Job(kind="chat", message="hi", callback_url="https://example.com/hook")
    await handler_for(broker).run(job)

    assert len(posts) == 1 and posts[0][1]["status"] == "done"
    assert posts[0][1]["done"]["result"]["reply"] == "Hello"
    assert await broker.hget(keys.job(job.job_id), "callback_error") == "HTTP 500"


async def test_deliver_reports_a_status_without_the_body(monkeypatch):
    transport = httpx.MockTransport(lambda _request: httpx.Response(500, text=SECRET))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        callback.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
    )
    assert await callback.deliver("https://example.com/hook", {"job_id": "1"}, 1) == "HTTP 500"
