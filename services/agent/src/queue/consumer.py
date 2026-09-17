"""The job consumer: reads jobs and runs up to `WORKER_CONCURRENCY` of them at once.

- A slot is taken before a job is read, so a job is never claimed while it cannot start.
- Stale jobs (a dead worker's) are swept for first, every half `BROKER_MIN_IDLE_MS`, then new
  ones are read. A job past `BROKER_MAX_DELIVERIES`, or whose payload is invalid, goes to
  `jobs:dead`; the handler is told so it can publish the error.
- A job is acked once its handler returns. A handler reports the job's own failures as
  events; if it raises (the broker failed mid-job), the job stays pending for reclaim.
- A broker error while reading is logged and the loop retries after a pause.
- Once `stop` is set no job starts: one read during shutdown is left pending, unacked, for
  another worker to reclaim; running jobs finish.
"""

import asyncio
from typing import Protocol

from loguru import logger
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.queue import keys, reclaim
from src.queue.models import Job
from src.queue.reclaim import Delivery

# Why a delivery was dead-lettered (the dead-letter stream and the worker log).
DEAD_INVALID_PAYLOAD = "invalid payload"
DEAD_UNFINISHED = "not finished in {deliveries} deliveries"

BLOCK_MS = 2000
RETRY_PAUSE_SECONDS = 1.0


class Handler(Protocol):
    async def run(self, job: Job) -> None: ...

    async def dead(self, job: Job, reason: str) -> None: ...


class Consumer:
    def __init__(
        self,
        broker: Redis,
        handler: Handler,
        name: str,
        *,
        concurrency: int,
        min_idle_ms: int,
        max_deliveries: int,
    ) -> None:
        self._broker = broker
        self._handler = handler
        self._name = name
        self._slots = asyncio.Semaphore(concurrency)
        self._min_idle_ms = min_idle_ms
        self._max_deliveries = max_deliveries
        self._in_flight: set[str] = set()
        self._cursor = keys.SCAN_START
        self._next_sweep = 0.0

    async def run(self, stop: asyncio.Event) -> None:
        """Consumes until `stop` is set, then lets the running jobs finish."""
        await reclaim.ensure_group(self._broker)
        keeper = asyncio.create_task(
            reclaim.keep_claimed(self._broker, self._name, self._in_flight, self._min_idle_ms)
        )
        try:
            async with asyncio.TaskGroup() as jobs:
                while not stop.is_set():
                    await self._slots.acquire()
                    if stop.is_set():
                        self._slots.release()
                        break
                    try:
                        delivery = await self.next_delivery()
                    except RedisError as exc:
                        self._slots.release()
                        logger.bind(error=type(exc).__name__).error("consumer.read_failed")
                        await asyncio.sleep(RETRY_PAUSE_SECONDS)
                        continue
                    if delivery is None:
                        self._slots.release()
                        # Yields even when the read did not block (a fake broker returns at once).
                        await asyncio.sleep(0)
                        continue
                    if stop.is_set():
                        # Read as shutdown began: not started, not acked, so redelivered.
                        self._slots.release()
                        logger.bind(entry_id=delivery.entry_id).warning("job.left_for_redelivery")
                        break
                    self._in_flight.add(delivery.entry_id)
                    jobs.create_task(self._dispatch(delivery))
        finally:
            keeper.cancel()

    async def next_delivery(self) -> Delivery | None:
        loop = asyncio.get_running_loop()
        if loop.time() >= self._next_sweep:
            self._cursor, stale = await reclaim.next_stale(
                self._broker, self._name, self._min_idle_ms, self._cursor
            )
            if stale is not None:
                logger.bind(entry_id=stale.entry_id, deliveries=stale.count).warning(
                    "job.reclaimed"
                )
                return stale
            if self._cursor == keys.SCAN_START:
                self._next_sweep = loop.time() + self._min_idle_ms / 2000
        return await reclaim.next_new(self._broker, self._name, BLOCK_MS)

    async def _dispatch(self, delivery: Delivery) -> None:
        try:
            await self.handle(delivery)
        except Exception:
            # Left pending: another sweep reclaims it and counts the delivery.
            logger.bind(entry_id=delivery.entry_id).exception("job.handler_failed")
        finally:
            self._in_flight.discard(delivery.entry_id)
            self._slots.release()

    async def handle(self, delivery: Delivery) -> None:
        """Runs, or dead-letters, one delivery, and acks it."""
        try:
            job = Job.model_validate_json(delivery.raw or "")
        except ValidationError:
            await reclaim.dead_letter(self._broker, delivery, DEAD_INVALID_PAYLOAD)
            return
        if delivery.count > self._max_deliveries:
            reason = DEAD_UNFINISHED.format(deliveries=self._max_deliveries)
            # The client hears first: a failed dead-letter redelivers it and it is told again.
            await self._handler.dead(job, reason)
            await reclaim.dead_letter(self._broker, delivery, reason)
            return
        await self._handler.run(job)
        await reclaim.ack(self._broker, delivery.entry_id)
