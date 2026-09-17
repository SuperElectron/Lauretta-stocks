"""The MCP server over real streamable HTTP: tools act for the gateway-named user alone."""

import asyncio
import contextlib
import socket

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from src.api.app import create_app
from src.api.mcpserver import desk, server
from src.queue import submit
from src.queue.models import Done, Job, Progress, Token
from tests.utils import settings


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.asynccontextmanager
async def running_api(broker):
    app = create_app(with_lifespan=False)
    server.bound.settings, server.bound.broker, server.bound.pool = settings(), broker, None
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    api = uvicorn.Server(config)
    async with server.mcp.session_manager.run():
        task = asyncio.create_task(api.serve())
        while not api.started:
            await asyncio.sleep(0.01)
        try:
            yield f"http://127.0.0.1:{port}/mcp/"
        finally:
            api.should_exit = True
            await task


@contextlib.asynccontextmanager
async def session(url: str, user: str | None):
    headers = {} if user is None else {"X-Lauretta-User": user}
    async with (
        httpx.AsyncClient(headers=headers) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
        ClientSession(read, write) as client,
    ):
        await client.initialize()
        yield client


@pytest.fixture(autouse=True)
def fresh_session_manager(monkeypatch):
    """The session manager runs once per instance; each test gets its own."""
    monkeypatch.setattr(server.mcp, "_session_manager", None)
    server.mcp.streamable_http_app()


@pytest.fixture
def no_threads_table(monkeypatch):
    async def create(*_args):
        return True

    monkeypatch.setattr(desk.threads, "create", create)


async def test_ask_assistant_queues_for_the_named_user_and_reports_progress(
    broker,
    worker,
    no_threads_table,  # noqa: ARG001
):
    worker.reply = lambda _job, _n: [
        Progress(stage="assistant", detail="reading your notes", name="the Director"),
        Token(text="hi"),
        Done(result={"thread_id": "mcp", "reply": "hi", "notices": []}),
    ]
    seen: list[str] = []

    async def on_progress(_progress, _total, message):
        seen.append(message)

    async with running_api(broker) as url, session(url, "max") as client:
        result = await client.call_tool(
            "ask_assistant", {"message": "hey"}, progress_callback=on_progress
        )
    assert not result.isError
    assert result.structuredContent == {"thread_id": "mcp", "reply": "hi", "notices": []}
    assert seen == ["the Director: reading your notes"]
    [job] = worker.jobs
    assert (job.user, job.kind, job.client.client) == ("max", "chat", "mcp")


async def test_a_request_without_a_user_is_refused(broker, worker):
    async with running_api(broker) as url, session(url, None) as client:
        result = await client.call_tool("holdings", {})
    assert result.isError
    assert not worker.jobs


async def test_an_unknown_user_is_refused(broker):
    async with running_api(broker) as url, session(url, "mallory") as client:
        result = await client.call_tool("start_research", {"ticker": "NVDA"})
    assert result.isError


async def test_another_users_job_is_not_found(broker):
    job = Job(kind="research", ticker="NVDA", user="mat")
    await submit.submit(broker, job, 60)
    async with running_api(broker) as url:
        async with session(url, "max") as client:
            theirs = await client.call_tool("get_job", {"job_id": job.job_id})
        async with session(url, "mat") as client:
            mine = await client.call_tool("get_job", {"job_id": job.job_id})
    assert theirs.isError
    assert not mine.isError
    assert mine.structuredContent["status"] == "queued"


async def test_holdings_are_read_for_the_named_user(broker, monkeypatch):
    asked: list[str] = []

    async def all_of(_pool, user):
        asked.append(user)
        return [{"ticker": "NVDA", "shares": 1}]

    monkeypatch.setattr(desk.holdings, "all_of", all_of)
    async with running_api(broker) as url, session(url, "max") as client:
        result = await client.call_tool("holdings", {})
    assert not result.isError
    assert asked == ["max"]


async def test_an_unexpected_failure_reaches_the_client_without_its_details(broker, monkeypatch):
    async def broken(_pool, _user):
        raise RuntimeError("password=hunter2 at db:5432")

    monkeypatch.setattr(desk.holdings, "all_of", broken)
    async with running_api(broker) as url, session(url, "mat") as client:
        result = await client.call_tool("holdings", {})
    assert result.isError
    text = result.content[0].text
    assert "hunter2" not in text and "5432" not in text
    assert "the desk could not do that" in text


async def test_an_invalid_ticker_names_the_field(broker):
    async with running_api(broker) as url, session(url, "mat") as client:
        result = await client.call_tool("start_research", {"ticker": "not a ticker!"})
    assert result.isError
    assert "ticker" in result.content[0].text
