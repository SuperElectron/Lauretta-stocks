"""A job's life on the broker: submitted by the API, marked by the worker, read by both.

The status hash `job:{id}` holds `status` (queued, running, done, failed), `kind`, timestamps,
and on failure `error_code`. It expires with the job's events.
"""

from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import WatchError

from src.queue import keys
from src.queue.models import Job

Status = Literal["queued", "running", "done", "failed"]
FINISHED: frozenset[str] = frozenset({"done", "failed"})
# The jobs stream is trimmed to about this many entries; a job's record is its hash and events.
JOBS_MAXLEN = 10_000


def now() -> str:
    return datetime.now(UTC).isoformat()


async def submit(broker: Redis, job: Job, ttl_s: int) -> None:
    """Records the job as queued and adds it to the `jobs` stream, in one transaction."""
    async with broker.pipeline(transaction=True) as pipe:
        _queue(pipe, job, ttl_s)
        await pipe.execute()


async def submit_once(broker: Redis, job: Job, ttl_s: int) -> bool:
    """As `submit`, unless a job with this id is already recorded: then nothing is queued and
    False is returned. Callers derive the id from the request, so a retry never runs twice."""
    async with broker.pipeline(transaction=True) as pipe:
        try:
            await pipe.watch(keys.job(job.job_id))
            if await pipe.exists(keys.job(job.job_id)):
                return False
            pipe.multi()
            _queue(pipe, job, ttl_s)
            await pipe.execute()
        except WatchError:
            # Another request recorded the same job between the check and the write.
            return False
    return True


def _queue(pipe: Pipeline, job: Job, ttl_s: int) -> None:
    pipe.hset(
        keys.job(job.job_id),
        mapping={"status": "queued", "kind": job.kind, "created_at": job.submitted_at},
    )
    pipe.expire(keys.job(job.job_id), ttl_s)
    pipe.xadd(
        keys.JOBS, {keys.PAYLOAD: job.model_dump_json()}, maxlen=JOBS_MAXLEN, approximate=True
    )


async def mark(broker: Redis, job_id: str, ttl_s: int, **fields: str) -> None:
    async with broker.pipeline(transaction=True) as pipe:
        pipe.hset(keys.job(job_id), mapping=fields)
        pipe.expire(keys.job(job_id), ttl_s)
        await pipe.execute()


async def status_of(broker: Redis, job_id: str) -> dict[str, str] | None:
    """The status hash, or None for a job never submitted or already expired."""
    found = await broker.hgetall(keys.job(job_id))
    return found or None
