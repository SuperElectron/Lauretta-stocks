import asyncio

import pytest
from fakeredis import FakeAsyncRedis

from src.errors import LockLost, ThreadBusy
from src.queue.lock import ThreadLock


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


async def test_a_second_job_on_the_thread_waits_then_fails_busy(broker):
    first = ThreadLock(broker, "main", ttl_ms=10_000, wait_ms=100)
    second = ThreadLock(broker, "main", ttl_ms=10_000, wait_ms=100)
    async with first.held():
        with pytest.raises(ThreadBusy):
            await second.acquire()
    await second.acquire()
    assert await broker.get("lock:thread:main") is not None


async def test_a_waiting_job_gets_the_lock_once_it_is_released(broker):
    first = ThreadLock(broker, "main", ttl_ms=10_000, wait_ms=2_000)
    second = ThreadLock(broker, "main", ttl_ms=10_000, wait_ms=2_000)
    await first.acquire()
    waiting = asyncio.create_task(second.acquire())
    await asyncio.sleep(0.1)
    assert not waiting.done()
    assert await first.release()
    await asyncio.wait_for(waiting, 2)


async def test_release_leaves_a_lock_another_job_has_taken_since(broker):
    first = ThreadLock(broker, "main", ttl_ms=10_000, wait_ms=100)
    await first.acquire()
    await broker.set("lock:thread:main", "someone-else")
    assert not await first.release()
    assert not await first.refresh()
    assert await broker.get("lock:thread:main") == "someone-else"


async def test_other_threads_are_not_blocked(broker):
    async with ThreadLock(broker, "main", 10_000, 100).held():
        async with ThreadLock(broker, "other", 10_000, 100).held():
            pass


async def test_the_lock_is_refreshed_while_the_job_runs(broker):
    lock = ThreadLock(broker, "main", ttl_ms=300, wait_ms=100)
    async with lock.held():
        await asyncio.sleep(0.5)
        assert await broker.get("lock:thread:main") is not None
        assert not lock.lost.is_set()
    assert await broker.get("lock:thread:main") is None


async def test_a_lost_lock_cancels_the_job(broker):
    lock = ThreadLock(broker, "main", ttl_ms=150, wait_ms=100)
    async with lock.held():
        await broker.set("lock:thread:main", "someone-else")
        with pytest.raises(LockLost):
            await lock.guard(asyncio.sleep(5))
