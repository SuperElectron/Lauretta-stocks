"""A job's event stream, read side: the worker appends; SSE and `?wait=` read, resuming by entry id.

Each entry has `type` (the SSE event name) and `data` (its JSON). Entry ids are the SSE ids,
so a client's `Last-Event-ID` is where its read resumes. The stream expires `EVENTS_TTL_S`
after its latest event.
"""

import asyncio
import math
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from redis.asyncio import Redis

from src.queue import keys, submit
from src.queue.models import TERMINAL

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


async def last_terminal(broker: Redis, job_id: str) -> StoredEvent | None:
    """The job's `done` or `error` event, if it published one (always its last event)."""
    for entry_id, fields in await broker.xrevrange(keys.events(job_id), count=1):
        if fields[keys.ENTRY_TYPE] in TERMINAL:
            return StoredEvent(entry_id, fields[keys.ENTRY_TYPE], fields[keys.ENTRY_DATA])
    return None


async def read(
    broker: Redis, job_id: str, after: str = keys.SCAN_START, deadline: float | None = None
) -> AsyncIterator[StoredEvent]:
    """Events after entry id `after`, as they arrive. Ends after `done` or `error`; at loop time
    `deadline` when one is given; or when a read finds nothing more and the job has finished
    or expired (its status hash is gone, or its events stream is gone after events were read).
    """
    loop = asyncio.get_running_loop()
    finishing = False
    while True:
        block_ms = READ_BLOCK_MS
        if deadline is not None:
            # Rounded up, so a read never gives up before the deadline itself.
            left_ms = math.ceil((deadline - loop.time()) * 1000)
            if left_ms <= 0:
                return
            block_ms = min(block_ms, left_ms)
        # Once the job is known finished, one more read without blocking picks up anything
        # published between the last read and that check.
        response = await broker.xread(
            {keys.events(job_id): after}, count=READ_COUNT, block=None if finishing else block_ms
        )
        entries = [entry for _stream, stream_entries in response for entry in stream_entries]
        if not entries:
            if finishing:
                return
            finishing = await _over(broker, job_id, read_any=after != keys.SCAN_START)
            # Yields even when the read did not block.
            await asyncio.sleep(0)
        for entry_id, fields in entries:
            after = entry_id
            yield StoredEvent(entry_id, fields[keys.ENTRY_TYPE], fields[keys.ENTRY_DATA])
            if fields[keys.ENTRY_TYPE] in TERMINAL:
                return


async def _over(broker: Redis, job_id: str, read_any: bool) -> bool:
    """Nothing more will be published: the job finished, or its records expired."""
    status = await broker.hget(keys.job(job_id), keys.STATUS)
    if status is None or status in submit.FINISHED:
        return True
    return read_any and not await broker.exists(keys.events(job_id))
