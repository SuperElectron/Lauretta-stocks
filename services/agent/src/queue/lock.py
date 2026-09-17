"""The per-thread lock: at most one chat job runs on a conversation at a time, across workers.

- `SET lock:thread:{id} <token> NX PX <ttl>` takes it; a job waits up to `AGENT_LOCK_WAIT_MS`,
  polling with backoff, then fails `ThreadBusy`.
- While held it is refreshed every third of its TTL by compare-and-pexpire. A refresh that
  finds another holder or no key marks it lost, and `guard` cancels the job with `LockLost`.
- It is released by compare-and-delete, so a lock another job has since taken is left alone.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from uuid import uuid4

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.errors import LockLost, ThreadBusy
from src.queue import keys

FIRST_POLL_SECONDS = 0.05
MAX_POLL_SECONDS = 1.0

_REFRESH = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class ThreadLock:
    def __init__(self, broker: Redis, thread_id: str, ttl_ms: int, wait_ms: int) -> None:
        self._broker = broker
        self.key = keys.thread_lock(thread_id)
        self._token = uuid4().hex
        self._ttl_ms = ttl_ms
        self._wait_ms = wait_ms
        self.lost = asyncio.Event()

    async def try_acquire(self) -> bool:
        return bool(await self._broker.set(self.key, self._token, nx=True, px=self._ttl_ms))

    async def acquire(self) -> None:
        """Takes the lock, waiting for its holder up to the wait limit, else `ThreadBusy`."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._wait_ms / 1000
        poll = FIRST_POLL_SECONDS
        while not await self.try_acquire():
            left = deadline - loop.time()
            if left <= 0:
                raise ThreadBusy
            await asyncio.sleep(min(poll, left))
            poll = min(poll * 2, MAX_POLL_SECONDS)

    async def refresh(self) -> bool:
        return bool(await self._broker.eval(_REFRESH, 1, self.key, self._token, self._ttl_ms))

    async def release(self) -> bool:
        """True when this job still held the lock and deleted it."""
        return bool(await self._broker.eval(_RELEASE, 1, self.key, self._token))

    @asynccontextmanager
    async def held(self) -> AsyncIterator["ThreadLock"]:
        await self.acquire()
        refresher = asyncio.create_task(self._keep())
        try:
            yield self
        finally:
            refresher.cancel()
            await asyncio.wait({refresher})
            if not await self.release():
                logger.bind(key=self.key).error("lock.lost_at_release")

    async def guard[T](self, work: Awaitable[T]) -> T:
        """Awaits `work`, cancelling it with `LockLost` if the lock is lost first."""
        task = asyncio.ensure_future(work)
        lost = asyncio.create_task(self.lost.wait())
        try:
            await asyncio.wait({task, lost}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            lost.cancel()
            if not task.done():
                task.cancel()
                await asyncio.wait({task})
        if task.cancelled() and self.lost.is_set():
            raise LockLost
        return task.result()

    async def _keep(self) -> None:
        while True:
            await asyncio.sleep(self._ttl_ms / 3000)
            try:
                held = await self.refresh()
            except RedisError as exc:
                # Retried on the next tick; two misses in a row leave a third of the TTL.
                logger.bind(key=self.key, error=type(exc).__name__).error("lock.refresh_failed")
                continue
            if not held:
                logger.bind(key=self.key).error("lock.lost")
                self.lost.set()
                return
