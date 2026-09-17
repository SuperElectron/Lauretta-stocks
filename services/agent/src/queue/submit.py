"""A job's life on the broker, worker side: the API submits it (`contracts/`); the worker marks it.

The status hash `job:{id}` holds `status` (queued, running, done, failed), `kind`, `user` (whose
job it is: the API answers anyone else as if it did not exist), timestamps, and on failure
`error_code`. It expires with the job's events.
"""

from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis

from src.queue import keys

Status = Literal["queued", "running", "done", "failed"]
FINISHED: frozenset[str] = frozenset({"done", "failed"})


def now() -> str:
    return datetime.now(UTC).isoformat()


async def mark(broker: Redis, job_id: str, ttl_s: int, **fields: str) -> None:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.hset(keys.job(job_id), mapping=fields)
        pipe.expire(keys.job(job_id), ttl_s)
        await pipe.execute()


async def status_of(broker: Redis, job_id: str) -> dict[str, str] | None:
    """The status hash, or None for a job never submitted or already expired."""
    found = await broker.hgetall(keys.job(job_id))
    return found or None
