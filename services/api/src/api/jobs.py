"""`POST /v1/jobs` queues a chat turn or research run; `GET /v1/jobs/{id}` reads its status.

Every job belongs to the user the gateway named, and only they can read it. The API never runs a
graph. With `?wait=N` the POST also follows the job's events for up to N
seconds: the outcome (200) if it finished, else 202 as without `wait`.
"""

import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from src.api.deps import BrokerDep, ClientDep, JobId, JobStatusDep, PoolDep, SettingsDep, UserDep
from src.db.queries import threads
from src.queue import events, keys, submit
from src.queue.models import Job, JobRequest

router = APIRouter()


def accepted(job_id: str) -> JSONResponse:
    body = {"job_id": job_id, "status": keys.QUEUED, "events_url": f"/v1/jobs/{job_id}/events"}
    return JSONResponse(body, status_code=202)


async def outcome(broker: Redis, job_id: str, wait_s: int) -> dict[str, Any] | None:
    """The job's `done` result or `error`, if it finishes within `wait_s`."""
    deadline = asyncio.get_running_loop().time() + wait_s
    async for event in events.read(broker, job_id, deadline=deadline):
        if event.type == "done":
            return {"job_id": job_id, "status": keys.DONE, **json.loads(event.data)}
        if event.type == "error":
            return {"job_id": job_id, "status": keys.FAILED, "error": json.loads(event.data)}
    return None


@router.post("/v1/jobs", status_code=202)
async def create_job(
    user: UserDep,
    request: JobRequest,
    broker: BrokerDep,
    pool: PoolDep,
    settings: SettingsDep,
    client: ClientDep,
    wait: Annotated[int | None, Query(ge=1)] = None,
) -> JSONResponse:
    job = Job(**request.model_dump(), user=user, client=client)
    if job.kind == "chat":
        await threads.create(pool, user, job.thread_id, client.client)
    await submit.submit(broker, job, settings.EVENTS_TTL_S)
    if wait is None:
        return accepted(job.job_id)
    finished = await outcome(broker, job.job_id, min(wait, settings.API_MAX_WAIT_S))
    return accepted(job.job_id) if finished is None else JSONResponse(finished)


@router.get("/v1/jobs/{job_id}")
async def job_status(job_id: JobId, status: JobStatusDep) -> dict[str, str]:
    return {"job_id": job_id, **{k: v for k, v in status.items() if k != keys.USER}}
