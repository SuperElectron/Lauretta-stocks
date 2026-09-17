"""Delivering jobs at least once: reading, reclaiming from dead workers, and dead-lettering.

- `next_new` reads a job no consumer has seen; its delivery count is 1.
- `next_stale` takes over one job pending longer than `BROKER_MIN_IDLE_MS` (its worker died),
  following the XAUTOCLAIM cursor, which scans a bounded part of the pending list per call.
- `keep_claimed` touches the jobs this worker still runs, so none is reclaimed from under it.
- `dead_letter` parks a job on `jobs:dead` with its reason, then acks it.
"""

import asyncio
from dataclasses import dataclass

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from src.queue import keys

NEW_ENTRIES = ">"


@dataclass(frozen=True)
class Delivery:
    entry_id: str
    # The raw payload, or None when the entry has no payload field.
    raw: str | None
    count: int


async def ensure_group(broker: Redis) -> None:
    """Creates the `workers` group on `jobs` (and the stream) unless it exists."""
    try:
        await broker.xgroup_create(keys.JOBS, keys.GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def next_new(broker: Redis, consumer: str, block_ms: int) -> Delivery | None:
    response = await broker.xreadgroup(
        keys.GROUP, consumer, {keys.JOBS: NEW_ENTRIES}, count=1, block=block_ms
    )
    for _stream, entries in response:
        for entry_id, fields in entries:
            return Delivery(entry_id, fields.get(keys.PAYLOAD), 1)
    return None


async def next_stale(
    broker: Redis, consumer: str, min_idle_ms: int, cursor: str
) -> tuple[str, Delivery | None]:
    """One job idle past `min_idle_ms`, now this consumer's, and the cursor to pass next
    (`SCAN_START` once the scan reached the end of the pending list)."""
    next_cursor, claimed, *_ = await broker.xautoclaim(
        keys.JOBS, keys.GROUP, consumer, min_idle_time=min_idle_ms, start_id=cursor, count=1
    )
    for entry_id, fields in claimed:
        pending = await broker.xpending_range(
            keys.JOBS, keys.GROUP, min=entry_id, max=entry_id, count=1
        )
        if not pending:
            # Acked by its owner between the claim and this read: nothing to run.
            return next_cursor, None
        count = int(pending[0]["times_delivered"])
        return next_cursor, Delivery(entry_id, fields.get(keys.PAYLOAD), count)
    return next_cursor, None


async def ack(broker: Redis, entry_id: str) -> None:
    await broker.xack(keys.JOBS, keys.GROUP, entry_id)


async def dead_letter(broker: Redis, delivery: Delivery, reason: str) -> None:
    """On `jobs:dead` before it leaves the pending list, so a failed ack only duplicates it."""
    logger.bind(entry_id=delivery.entry_id, deliveries=delivery.count, reason=reason).error(
        "job.dead_lettered"
    )
    await broker.xadd(
        keys.DEAD,
        {"entry_id": delivery.entry_id, keys.PAYLOAD: delivery.raw or "", "reason": reason},
    )
    await ack(broker, delivery.entry_id)


async def keep_claimed(broker: Redis, consumer: str, in_flight: set[str], min_idle_ms: int) -> None:
    """Every third of `min_idle_ms`, resets the idle time of the jobs in `in_flight`
    (XCLAIM with JUSTID, which leaves their delivery counts alone)."""
    while True:
        await asyncio.sleep(min_idle_ms / 3000)
        if not in_flight:
            continue
        try:
            await broker.xclaim(
                keys.JOBS, keys.GROUP, consumer, min_idle_time=0,
                message_ids=sorted(in_flight), justid=True,
            )  # fmt: skip
        except RedisError as exc:
            logger.bind(error=type(exc).__name__).error("consumer.keepalive_failed")
