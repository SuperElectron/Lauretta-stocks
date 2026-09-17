"""A job's event stream, worker side: the worker appends events; the API reads them.

The desk also reads one: a chat turn follows the research it started, so the investor watches the
team work (`src/runs.py`).

Each entry has `type` (the event name) and `data` (its JSON); `contracts/queue_keys.v1.json` and
`contracts/job_events.v1.json` pin both. The stream expires `EVENTS_TTL_S` after its latest event.
"""

import asyncio
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass

from redis.asyncio import Redis

from src.queue import keys, submit
from src.queue.models import TERMINAL, Event

READ_BLOCK_MS = 5000
READ_COUNT = 100


@dataclass(frozen=True)
class StoredEvent:
    id: str
    type: str
    # The event's fields as JSON, passed through to the client untouched.
    data: str


async def publish(broker: Redis, job_id: str, event: Event, ttl_s: int) -> str:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.xadd(
            keys.events(job_id),
            {keys.ENTRY_TYPE: event.type, keys.ENTRY_DATA: event.model_dump_json()},
        )
        pipe.expire(keys.events(job_id), ttl_s)
        entry_id, _ = await pipe.execute()
    return entry_id


async def follow(broker: Redis, job_id: str, deadline: float) -> AsyncIterator[StoredEvent]:
    """The job's events as they arrive, until it ends or loop time `deadline` passes.

    A job that is already finished, or whose records are gone, ends the read at once; whatever
    is not read by the deadline stays on the stream for whoever reads it next.
    """
    loop = asyncio.get_running_loop()
    after = keys.SCAN_START
    while True:
        left_ms = math.ceil((deadline - loop.time()) * 1000)
        if left_ms <= 0:
            return
        response = await broker.xread(
            {keys.events(job_id): after}, count=READ_COUNT, block=min(READ_BLOCK_MS, left_ms)
        )
        entries = [entry for _stream, stream_entries in response for entry in stream_entries]
        if not entries and await _over(broker, job_id):
            return
        for entry_id, fields in entries:
            after = entry_id
            yield StoredEvent(entry_id, fields[keys.ENTRY_TYPE], fields[keys.ENTRY_DATA])
            if fields[keys.ENTRY_TYPE] in TERMINAL:
                return


async def _over(broker: Redis, job_id: str) -> bool:
    """Nothing more will be published: the job finished, or its records expired."""
    status = await broker.hget(keys.job(job_id), keys.STATUS)
    return status is None or status in submit.FINISHED


async def last_terminal(broker: Redis, job_id: str) -> StoredEvent | None:
    """The job's `done` or `error` event, if it published one (always its last event)."""
    for entry_id, fields in await broker.xrevrange(keys.events(job_id), count=1):
        if fields[keys.ENTRY_TYPE] in TERMINAL:
            return StoredEvent(entry_id, fields[keys.ENTRY_TYPE], fields[keys.ENTRY_DATA])
    return None
