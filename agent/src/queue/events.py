"""A job's event stream: the worker appends, SSE and `?wait=` read, resuming by entry id.

Each entry has `type` (the SSE event name) and `data` (its JSON). Entry ids are the SSE ids,
so a client's `Last-Event-ID` is where its read resumes. The stream expires `EVENTS_TTL_S`
after its latest event.
"""

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from redis.asyncio import Redis

from src.queue import keys
from src.queue.models import TERMINAL, Event

READ_BLOCK_MS = 5000
READ_COUNT = 100
_ENTRY_ID = re.compile(r"\d{1,20}-\d{1,20}")


@dataclass(frozen=True)
class StoredEvent:
    id: str
    type: str
    # The event's fields as JSON, passed through to the client untouched.
    data: str


def is_entry_id(value: str) -> bool:
    return _ENTRY_ID.fullmatch(value) is not None


async def publish(broker: Redis, job_id: str, event: Event, ttl_s: int) -> str:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.xadd(keys.events(job_id), {"type": event.type, "data": event.model_dump_json()})
        pipe.expire(keys.events(job_id), ttl_s)
        entry_id, _ = await pipe.execute()
    return entry_id


async def count(broker: Redis, job_id: str) -> int:
    return await broker.xlen(keys.events(job_id))


async def read(
    broker: Redis, job_id: str, after: str = keys.SCAN_START, deadline: float | None = None
) -> AsyncIterator[StoredEvent]:
    """Events after entry id `after`, as they arrive, ending after `done` or `error`, or
    at loop time `deadline` when one is given."""
    loop = asyncio.get_running_loop()
    while True:
        block_ms = READ_BLOCK_MS
        if deadline is not None:
            left_ms = int((deadline - loop.time()) * 1000)
            if left_ms <= 0:
                return
            block_ms = min(block_ms, left_ms)
        response = await broker.xread(
            {keys.events(job_id): after}, count=READ_COUNT, block=block_ms
        )
        if not response:
            # Yields even when the read did not block (a fake broker returns at once).
            await asyncio.sleep(0)
        for _stream, entries in response:
            for entry_id, fields in entries:
                after = entry_id
                yield StoredEvent(entry_id, fields["type"], fields["data"])
                if fields["type"] in TERMINAL:
                    return
