"""What the API does on the broker, for the worker's tests: queue a job. The worker never does
this; `contracts/` pins the payload and keys both sides use."""

from redis.asyncio import Redis

from src.queue import keys
from src.queue.models import Job


async def submit(broker: Redis, job: Job, ttl_s: int) -> None:
    """Records the job as queued and adds it to the `jobs` stream, as the API does."""
    async with broker.pipeline(transaction=True) as pipe:
        pipe.hset(
            keys.job(job.job_id),
            mapping={
                "status": "queued",
                "kind": job.kind,
                "user": job.user,
                "created_at": job.submitted_at,
            },
        )
        pipe.expire(keys.job(job.job_id), ttl_s)
        pipe.xadd(keys.JOBS, {keys.PAYLOAD: job.model_dump_json()})
        await pipe.execute()
