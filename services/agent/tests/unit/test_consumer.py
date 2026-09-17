import asyncio

import pytest
from fakeredis import FakeAsyncRedis

from src.queue import keys, reclaim
from src.queue.consumer import Consumer
from src.queue.models import Job
from src.queue.submit import submit


class RecordingHandler:
    def __init__(self, fail: bool = False) -> None:
        self.ran: list[str] = []
        self.dead_jobs: list[tuple[str, str]] = []
        self.fail = fail

    async def run(self, job: Job) -> None:
        self.ran.append(job.job_id)
        if self.fail:
            raise ConnectionError("broker went away mid-job")

    async def dead(self, job: Job, reason: str) -> None:
        self.dead_jobs.append((job.job_id, reason))


@pytest.fixture
async def broker():
    client = FakeAsyncRedis(decode_responses=True)
    await reclaim.ensure_group(client)
    return client


def consumer(broker, handler, name="w1", min_idle_ms=60_000, max_deliveries=2):
    return Consumer(
        broker,
        handler,
        name,
        concurrency=2,
        min_idle_ms=min_idle_ms,
        max_deliveries=max_deliveries,
    )


async def pending(broker) -> int:
    return (await broker.xpending(keys.JOBS, keys.GROUP))["pending"]


async def test_a_job_runs_once_and_is_acked(broker):
    job = Job(kind="chat", message="hi")
    await submit(broker, job, ttl_s=60)
    handler = RecordingHandler()
    worker = consumer(broker, handler)

    delivery = await worker.next_delivery()
    await worker.handle(delivery)

    assert handler.ran == [job.job_id]
    assert await pending(broker) == 0
    assert await broker.hget(keys.job(job.job_id), "status") == "queued"


async def test_a_job_whose_handler_raises_stays_pending_and_is_reclaimed(broker):
    await submit(broker, Job(kind="research", ticker="MSFT"), ttl_s=60)
    first = consumer(broker, RecordingHandler(fail=True), "w1", min_idle_ms=1)
    delivery = await first.next_delivery()
    with pytest.raises(ConnectionError):
        await first.handle(delivery)
    assert await pending(broker) == 1

    await asyncio.sleep(0.01)
    handler = RecordingHandler()
    second = consumer(broker, handler, "w2", min_idle_ms=1)
    again = await second.next_delivery()
    assert (again.entry_id, again.count) == (delivery.entry_id, 2)
    await second.handle(again)
    assert len(handler.ran) == 1 and await pending(broker) == 0


async def test_a_job_past_max_deliveries_is_dead_lettered_not_run(broker):
    job = Job(kind="chat", message="hi")
    await submit(broker, job, ttl_s=60)
    handler = RecordingHandler()
    worker = consumer(broker, handler, min_idle_ms=1, max_deliveries=1)
    await worker.next_delivery()  # delivered once, never finished
    await asyncio.sleep(0.01)

    again = await worker.next_delivery()
    assert again.count == 2
    await worker.handle(again)

    assert handler.ran == []
    assert handler.dead_jobs == [(job.job_id, "not finished in 1 deliveries")]
    (dead,) = await broker.xrange(keys.DEAD)
    assert Job.model_validate_json(dead[1][keys.PAYLOAD]).job_id == job.job_id
    assert await pending(broker) == 0


async def test_an_invalid_payload_is_dead_lettered(broker):
    await broker.xadd(keys.JOBS, {keys.PAYLOAD: '{"kind": "trade"}'})
    handler = RecordingHandler()
    worker = consumer(broker, handler)
    await worker.handle(await worker.next_delivery())

    assert handler.ran == [] and handler.dead_jobs == []
    assert (await broker.xrange(keys.DEAD))[0][1]["reason"] == "invalid payload"
    assert await pending(broker) == 0


async def test_run_consumes_until_stopped(broker):
    jobs = [Job(kind="chat", message=str(n)) for n in range(3)]
    for job in jobs:
        await submit(broker, job, ttl_s=60)
    handler = RecordingHandler()
    stop = asyncio.Event()
    running = asyncio.create_task(consumer(broker, handler).run(stop))
    for _ in range(100):
        if len(handler.ran) == 3:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(running, 5)
    assert sorted(handler.ran) == sorted(job.job_id for job in jobs)
    assert await pending(broker) == 0


async def test_after_stop_no_new_job_starts_and_running_ones_finish(broker):
    first, second = Job(kind="chat", message="1"), Job(kind="chat", message="2")
    await submit(broker, first, ttl_s=60)
    await submit(broker, second, ttl_s=60)
    release, started = asyncio.Event(), asyncio.Event()

    class Slow(RecordingHandler):
        async def run(self, job: Job) -> None:
            await super().run(job)
            started.set()
            await release.wait()

    handler = Slow()
    stop = asyncio.Event()
    worker = Consumer(broker, handler, "w1", concurrency=1, min_idle_ms=60_000, max_deliveries=2)
    running = asyncio.create_task(worker.run(stop))
    await started.wait()
    stop.set()  # SIGTERM while the first job runs and the loop waits for its slot
    release.set()
    await asyncio.wait_for(running, 5)

    assert handler.ran == [first.job_id]
    assert await pending(broker) == 0
    later = await reclaim.next_new(broker, "w2", 10)
    assert Job.model_validate_json(later.raw).job_id == second.job_id


async def test_a_job_read_as_stop_is_set_is_left_pending_for_redelivery(broker, monkeypatch):
    job = Job(kind="chat", message="hi")
    await submit(broker, job, ttl_s=60)
    handler = RecordingHandler()
    worker = consumer(broker, handler)
    stop = asyncio.Event()
    read = worker.next_delivery

    async def read_then_stop():
        delivery = await read()
        stop.set()
        return delivery

    monkeypatch.setattr(worker, "next_delivery", read_then_stop)
    await asyncio.wait_for(worker.run(stop), 5)

    assert handler.ran == []
    assert await pending(broker) == 1


def test_the_broker_socket_timeout_outlasts_every_blocking_read():
    from src.queue import broker, events
    from src.queue.consumer import BLOCK_MS

    client = broker.connect("redis://127.0.0.1:1/0")
    timeout = client.connection_pool.connection_kwargs["socket_timeout"]
    assert timeout > events.READ_BLOCK_MS / 1000 and timeout > BLOCK_MS / 1000
