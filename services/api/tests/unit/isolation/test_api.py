"""Isolation at the API: the gateway's user header is the only identity, and one user's jobs,
events, reads, threads and models are never another's."""

import asyncio

import pytest

from src.api import reads
from src.queue import keys
from src.queue.models import Done, Token
from tests import worker_side
from tests.unit.isolation.conftest import queued
from tests.unit.openai.conftest import FakeWorker, body, client_for

pytestmark = pytest.mark.usefixtures("db")
UNKNOWN_JOB = "0" * 32


ROUTES = [
    ("POST", "/v1/jobs", {"kind": "chat", "message": "hi"}),
    ("GET", f"/v1/jobs/{UNKNOWN_JOB}", None),
    ("GET", f"/v1/jobs/{UNKNOWN_JOB}/events", None),
    ("GET", "/v1/holdings", None),
    ("GET", "/v1/theses/NVDA", None),
    ("GET", "/v1/models", None),
    ("POST", "/v1/chat/completions", body("hello")),
]


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Lauretta-User": "someone"}, {"X-Lauretta-User": ""}, {"X-Lauretta-User": "MAT"}],
    ids=["none", "unknown", "empty", "not-an-id"],
)
@pytest.mark.parametrize(("method", "path", "payload"), ROUTES, ids=[r[1] for r in ROUTES])
async def test_every_v1_route_refuses_a_request_without_an_allowed_user(
    broker, method, path, payload, headers
):
    async with client_for(broker, user=None) as client:
        response = await client.request(method, path, json=payload, headers=headers)
    assert response.status_code == 401
    assert await broker.exists(keys.JOBS) == 0


async def test_a_repeated_user_header_is_refused(broker):
    async with client_for(broker, user=None) as client:
        headers = [("X-Lauretta-User", "max"), ("X-Lauretta-User", "mat")]
        response = await client.get("/v1/holdings", headers=headers)
    assert response.status_code == 401


async def test_a_body_can_never_name_the_user(broker):
    async with client_for(broker) as client:
        payload = {"kind": "chat", "message": "hi", "user": "max"}
        response = await client.post("/v1/jobs", json=payload)
    assert response.status_code == 422
    assert await broker.exists(keys.JOBS) == 0


async def test_max_gets_404_for_mats_job_status_and_events_before_any_stream(broker):
    async with client_for(broker) as mat, client_for(broker, user="max") as max_:
        job_id = (await mat.post("/v1/jobs", json={"kind": "chat", "message": "hi"})).json()[
            "job_id"
        ]
        await worker_side.publish(broker, job_id, Token(text="Mat's secret"), 60)
        await worker_side.publish(broker, job_id, Done(result={"reply": "Mat's secret"}), 60)

        status = await max_.get(f"/v1/jobs/{job_id}")
        stream = await asyncio.wait_for(max_.get(f"/v1/jobs/{job_id}/events"), 2)
        own = await mat.get(f"/v1/jobs/{job_id}")

    assert (status.status_code, status.json()["detail"]["code"]) == (404, "JOB_NOT_FOUND")
    assert stream.status_code == 404
    assert not stream.headers["content-type"].startswith("text/event-stream")
    assert "secret" not in status.text + stream.text
    assert own.status_code == 200 and "user" not in own.json()


async def test_jobs_carry_the_callers_user_and_waiting_returns_only_their_outcome(broker):
    worker = FakeWorker(broker)
    worker.reply = lambda job, _n: [Done(result={"reply": f"for {job.user}"})]
    running = asyncio.create_task(worker.run())
    try:
        async with client_for(broker, user="max") as max_:
            response = await max_.post("/v1/jobs?wait=5", json={"kind": "chat", "message": "hi"})
    finally:
        running.cancel()
    assert response.json()["result"] == {"reply": "for max"}
    assert [job.user for job in await queued(broker)] == ["max"]


async def test_reads_ask_for_the_callers_rows_only(broker, monkeypatch):
    asked = []

    async def all_of(_pool, user_id):
        asked.append(("holdings", user_id))
        return []

    async def latest(_pool, user_id, _ticker):
        asked.append(("thesis", user_id))
        return None

    monkeypatch.setattr(reads.holdings, "all_of", all_of)
    monkeypatch.setattr(reads.theses, "latest", latest)
    async with client_for(broker, user="max") as max_:
        await max_.get("/v1/holdings")
        await max_.get("/v1/theses/NVDA")
    assert asked == [("holdings", "max"), ("thesis", "max")]


async def test_both_users_on_thread_main_get_separate_threads_locks_and_queues(broker, db):
    async with client_for(broker) as mat, client_for(broker, user="max") as max_:
        await mat.post("/v1/jobs", json={"kind": "chat", "message": "mine", "thread_id": "main"})
        await max_.post("/v1/jobs", json={"kind": "chat", "message": "his", "thread_id": "main"})
    jobs = await queued(broker)
    assert [(job.user, job.thread_id) for job in jobs] == [("mat", "main"), ("max", "main")]
    assert db.threads == {("mat", "main"), ("max", "main")}
    assert keys.thread("mat", "main") != keys.thread("max", "main")
    assert keys.thread_lock("mat", "main") != keys.thread_lock("max", "main")


async def test_a_thread_id_cannot_reach_into_another_users_namespace():
    # Max naming the key Mat's thread lives under still lands in Max's own namespace.
    assert keys.thread("max", keys.thread("mat", "main")) == "max:mat:main"
    assert not keys.thread("max", "mat:main").startswith("mat:")
