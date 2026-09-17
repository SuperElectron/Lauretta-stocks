"""A job's life on the broker, API side: submitted here, marked by the worker, read here.

The status hash `job:{id}` holds `status` (queued, running, done, failed), `kind`, `user` (whose
job it is: the API answers anyone else as if it did not exist), timestamps, and on failure
`error_code`. It expires with the job's events.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import WatchError

from src.queue import keys
from src.queue.models import Job

Status = Literal["queued", "running", "done", "failed"]
FINISHED: frozenset[str] = frozenset({keys.DONE, keys.FAILED})
# The jobs stream is trimmed to about this many entries; a job's record is its hash and events.
JOBS_MAXLEN = 10_000


def now() -> str:
    return datetime.now(UTC).isoformat()


async def submit(broker: Redis, job: Job, ttl_s: int) -> None:
    """Records the job as queued and adds it to the `jobs` stream, in one transaction."""
    async with broker.pipeline(transaction=True) as pipe:
        _queue(pipe, job, ttl_s)
        await pipe.execute()


@dataclass(frozen=True)
class Queued:
    job_id: str
    thread_id: str
    # The request named a job already queued (a retry), so nothing new was queued.
    attached: bool = False
    # Another job was still queued or running on the thread when this one was queued.
    behind: bool = False


async def attachable(broker: Redis | Pipeline, request_key: str) -> Queued | None:
    """The job a request record names, unless it failed or expired: a failed turn is run again."""
    record = await broker.get(request_key)
    if record is None:
        return None
    job_id, thread_id = record.split(" ", 1)
    status = await broker.hget(keys.job(job_id), keys.STATUS)
    return None if status in (None, keys.FAILED) else Queued(job_id, thread_id, attached=True)


async def submit_once(
    broker: Redis, job: Job, ttl_s: int, request_key: str, request_ttl_s: int
) -> Queued:
    """Queues `job` and records it under `request_key` for `request_ttl_s`, in one transaction,
    unless the record already names a live job: then that job is returned, attached."""
    async with broker.pipeline(transaction=True) as pipe:
        while True:
            try:
                await pipe.watch(request_key, keys.thread_job(job.user, job.thread_id))
                existing = await attachable(pipe, request_key)
                if existing is not None:
                    return existing
                previous = await pipe.get(keys.thread_job(job.user, job.thread_id))
                status = previous and await pipe.hget(keys.job(previous), keys.STATUS)
                pipe.multi()
                pipe.set(request_key, f"{job.job_id} {job.thread_id}", ex=request_ttl_s)
                pipe.set(keys.thread_job(job.user, job.thread_id), job.job_id, ex=ttl_s)
                _queue(pipe, job, ttl_s)
                await pipe.execute()
                return Queued(
                    job.job_id, job.thread_id, behind=status in (keys.QUEUED, keys.RUNNING)
                )
            except WatchError:
                # A request on the same key or thread won the race; look again.
                continue


async def release(broker: Redis, request_key: str, job_id: str) -> None:
    """Forgets a request whose answer was delivered, so sending it again runs a new turn."""
    record = await broker.get(request_key)
    if record is not None and record.split(" ", 1)[0] == job_id:
        await broker.delete(request_key)


def _queue(pipe: Pipeline, job: Job, ttl_s: int) -> None:
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


async def status_of(broker: Redis, job_id: str) -> dict[str, str] | None:
    """The status hash, or None for a job never submitted or already expired."""
    found = await broker.hgetall(keys.job(job_id))
    return found or None
