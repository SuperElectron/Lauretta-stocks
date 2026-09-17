"""What the worker does on the broker, for tests: publish a job's events and mark its status.
The API never does either; `contracts/` pins the formats both sides use."""

from redis.asyncio import Redis

from src.queue import keys
from src.queue.models import Event


async def publish(broker: Redis, job_id: str, event: Event, ttl_s: int) -> str:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.xadd(keys.events(job_id), {"type": event.type, "data": event.model_dump_json()})
        pipe.expire(keys.events(job_id), ttl_s)
        entry_id, _ = await pipe.execute()
    return entry_id


async def mark(broker: Redis, job_id: str, ttl_s: int, **fields: str) -> None:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.hset(keys.job(job_id), mapping=fields)
        pipe.expire(keys.job(job_id), ttl_s)
        await pipe.execute()
