import asyncio
import json

import fastapi.routing
import httpx
import pytest
from fakeredis import FakeAsyncRedis

from src.api.app import create_app
from src.queue import events, keys
from src.queue.models import Done, Error, Job, Progress, Token
from tests.utils import settings


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
async def client(broker):
    app = create_app(with_lifespan=False)
    app.state.settings, app.state.broker, app.state.pool = settings(API_MAX_WAIT_S=5), broker, None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as http:
        yield http


async def queued_job(broker) -> Job:
    ((_, entries),) = await broker.xread({keys.JOBS: "0-0"})
    return Job.model_validate_json(entries[-1][1][keys.PAYLOAD])


def parse_sse(body: str) -> list[dict[str, str]]:
    frames = []
    for block in body.strip().split("\n\n"):
        frame = {}
        for line in block.split("\n"):
            key, _, value = (
                line.partition(": ") if not line.startswith(":") else ("comment", "", line)
            )
            frame[key] = value
        frames.append(frame)
    return frames


async def test_post_queues_the_job_with_forwarded_client_info(client, broker):
    response = await client.post(
        "/v1/jobs",
        json={"kind": "chat", "message": "hi", "thread_id": "phone"},
        headers={
            "X-Forwarded-For": "100.64.0.7, 10.0.0.2",
            "User-Agent": "ua/1",
            "X-Client-Name": "ios",
        },
    )

    assert response.status_code == 202
    body = response.json()
    job = await queued_job(broker)
    assert body == {
        "job_id": job.job_id,
        "status": "queued",
        "events_url": f"/v1/jobs/{job.job_id}/events",
    }
    assert (job.thread_id, job.message, job.client.ip, job.client.client) == (
        "phone",
        "hi",
        "100.64.0.7",
        "ios",
    )
    status = (await client.get(f"/v1/jobs/{job.job_id}")).json()
    assert status["status"] == "queued" and status["kind"] == "chat"


async def test_invalid_jobs_are_refused_before_queueing(client, broker):
    response = await client.post("/v1/jobs", json={"kind": "research", "message": "hi"})
    assert response.status_code == 422
    assert await broker.exists(keys.JOBS) == 0


async def test_unknown_jobs_are_404(client):
    assert (await client.get("/v1/jobs/nope")).status_code == 404
    assert (await client.get("/v1/jobs/nope/events")).status_code == 404


async def test_wait_returns_the_result_when_the_job_finishes_in_time(client, broker):
    async def worker():
        while not await broker.exists(keys.JOBS):
            await asyncio.sleep(0.01)
        job = await queued_job(broker)
        await events.publish(broker, job.job_id, Token(text="Hi"), 60)
        await events.publish(broker, job.job_id, Done(result={"reply": "Hi"}), 60)

    working = asyncio.create_task(worker())
    response = await client.post("/v1/jobs?wait=5", json={"kind": "chat", "message": "hi"})
    await working
    assert response.status_code == 200
    assert response.json()["status"] == "done" and response.json()["result"] == {"reply": "Hi"}


async def test_wait_returns_202_when_the_job_is_still_running(client):
    response = await client.post("/v1/jobs?wait=1", json={"kind": "research", "ticker": "MSFT"})
    assert response.status_code == 202


async def test_sse_streams_named_events_with_stream_ids_and_ends_after_error(client, broker):
    job_id = await submitted(client)
    first = await events.publish(broker, job_id, Progress(stage="analyst", detail="drafting"), 60)
    await events.publish(broker, job_id, Error(code="THREAD_BUSY", message="busy"), 60)
    await events.publish(broker, job_id, Token(text="never sent"), 60)

    response = await client.get(f"/v1/jobs/{job_id}/events")

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    frames = parse_sse(response.text)
    assert [f["event"] for f in frames] == ["progress", "error"]
    assert frames[0]["id"] == first
    assert json.loads(frames[0]["data"]) == {"stage": "analyst", "detail": "drafting"}


async def test_sse_resumes_after_last_event_id(client, broker):
    job_id = await submitted(client)
    first = await events.publish(broker, job_id, Token(text="Hel"), 60)
    await events.publish(broker, job_id, Token(text="lo"), 60)
    await events.publish(broker, job_id, Done(result={}), 60)

    response = await client.get(f"/v1/jobs/{job_id}/events", headers={"Last-Event-ID": first})

    frames = parse_sse(response.text)
    assert [(f["event"], f["data"]) for f in frames] == [
        ("token", '{"text":"lo"}'),
        ("done", '{"result":{}}'),
    ]


async def test_sse_refuses_a_malformed_last_event_id(client):
    job_id = await submitted(client)
    response = await client.get(f"/v1/jobs/{job_id}/events", headers={"Last-Event-ID": "abc"})
    assert response.status_code == 400


async def test_sse_pings_while_the_job_is_quiet(client, broker, monkeypatch):
    monkeypatch.setattr(fastapi.routing, "_PING_INTERVAL", 0.05)
    job_id = await submitted(client)

    async def finish_later():
        await asyncio.sleep(0.3)
        await events.publish(broker, job_id, Done(result={}), 60)

    finishing = asyncio.create_task(finish_later())
    response = await client.get(f"/v1/jobs/{job_id}/events")
    await finishing
    assert ": ping" in response.text
    assert parse_sse(response.text)[-1]["event"] == "done"


async def submitted(client) -> str:
    response = await client.post("/v1/jobs", json={"kind": "chat", "message": "hi"})
    return response.json()["job_id"]


async def test_healthz_names_what_is_down(client, monkeypatch):
    from src.api import reads

    async def db_up(_pool, _sql):
        return [{"?column?": 1}]

    assert (await client.get("/healthz")).status_code == 503  # no pool in this app
    monkeypatch.setattr(reads, "rows", db_up)
    response = await client.get("/healthz")
    assert (response.status_code, response.json()) == (200, {"db": "ok", "broker": "ok"})


async def test_reads_return_saved_theses_and_holdings(client, monkeypatch):
    from src.api import reads

    async def latest(_pool, user_id, ticker):
        return {"ticker": ticker.upper(), "user": user_id} if ticker == "msft" else None

    async def all_of(_pool, _user_id):
        return [{"ticker": "MSFT", "shares": 10.0}]

    monkeypatch.setattr(reads.theses, "latest", latest)
    monkeypatch.setattr(reads.holdings, "all_of", all_of)
    assert (await client.get("/v1/theses/msft")).json() == {"ticker": "MSFT", "user": "friend"}
    assert (await client.get("/v1/theses/zzz")).status_code == 404
    assert (await client.get("/v1/holdings")).json() == {
        "holdings": [{"ticker": "MSFT", "shares": 10.0}]
    }
