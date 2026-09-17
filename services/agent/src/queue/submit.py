"""A job's life on the broker, worker side: the API submits it (`contracts/`); the worker marks it.

The status hash `job:{id}` holds `status` (queued, running, done, failed), `kind`, `user` (whose
job it is: the API answers anyone else as if it did not exist), timestamps, and on failure
`error_code`. It expires with the job's events.
"""

from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis

from src.queue import keys
from src.queue.models import Job

Status = Literal["queued", "running", "done", "failed"]
FINISHED: frozenset[str] = frozenset({keys.DONE, keys.FAILED})


def now() -> str:
    return datetime.now(UTC).isoformat()


# The jobs stream is trimmed to about this many entries; a job's record is its hash and events.
JOBS_MAXLEN = 10_000


async def enqueue(broker: Redis, job: Job, ttl_s: int) -> None:
    """Records the job as queued and adds it to the `jobs` stream, in one transaction.

    The desk queues its own research this way; every other job comes from the API, whose submit
    is the same write (`contracts/job.v1.json`).
    """
    async with broker.pipeline(transaction=True) as pipe:
        pipe.hset(
            keys.job(job.job_id),
            mapping={
                keys.STATUS: keys.QUEUED,
                keys.KIND: job.kind,
                keys.USER: job.user,
                keys.CREATED_AT: job.submitted_at,
            },
        )
        pipe.expire(keys.job(job.job_id), ttl_s)
        pipe.xadd(
            keys.JOBS, {keys.PAYLOAD: job.model_dump_json()}, maxlen=JOBS_MAXLEN, approximate=True
        )
        await pipe.execute()


async def mark(broker: Redis, job_id: str, ttl_s: int, **fields: str) -> None:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.hset(keys.job(job_id), mapping=fields)
        pipe.expire(keys.job(job_id), ttl_s)
        await pipe.execute()


async def status_of(broker: Redis, job_id: str) -> dict[str, str] | None:
    """The status hash, or None for a job never submitted or already expired."""
    found = await broker.hgetall(keys.job(job_id))
    return found or None
