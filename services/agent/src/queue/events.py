"""A job's event stream, worker side: the worker appends events; the API reads them.

Each entry has `type` (the event name) and `data` (its JSON); `contracts/queue_keys.v1.json` and
`contracts/job_events.v1.json` pin both. The stream expires `EVENTS_TTL_S` after its latest event.
"""

from dataclasses import dataclass

from redis.asyncio import Redis

from src.queue import keys
from src.queue.models import TERMINAL, Event


@dataclass(frozen=True)
class StoredEvent:
    id: str
    type: str
    # The event's fields as JSON, passed through to the client untouched.
    data: str


async def publish(broker: Redis, job_id: str, event: Event, ttl_s: int) -> str:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.xadd(keys.events(job_id), {"type": event.type, "data": event.model_dump_json()})
        pipe.expire(keys.events(job_id), ttl_s)
        entry_id, _ = await pipe.execute()
    return entry_id


async def last_terminal(broker: Redis, job_id: str) -> StoredEvent | None:
    """The job's `done` or `error` event, if it published one (always its last event)."""
    for entry_id, fields in await broker.xrevrange(keys.events(job_id), count=1):
        if fields["type"] in TERMINAL:
            return StoredEvent(entry_id, fields["type"], fields["data"])
    return None
