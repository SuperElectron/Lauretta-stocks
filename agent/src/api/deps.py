"""What routes take from the app's state and from the request's forwarded headers."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

from src.queue import submit
from src.queue.models import ClientInfo
from src.settings import Settings


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _broker(request: Request) -> Redis:
    return request.app.state.broker


def _pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool


SettingsDep = Annotated[Settings, Depends(_settings)]
BrokerDep = Annotated[Redis, Depends(_broker)]
PoolDep = Annotated[AsyncConnectionPool, Depends(_pool)]


def client_info(request: Request) -> ClientInfo:
    """The gateway authenticates and forwards who called: the first `X-Forwarded-For` hop,
    and `X-Client-Name` when the app sends one, else its `User-Agent`."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else None)
    name = request.headers.get("x-client-name") or request.headers.get("user-agent")
    return ClientInfo(ip=ip, client=name)


async def existing_job(job_id: str, broker: BrokerDep) -> dict[str, str]:
    """The job's status hash, or 404 for a job never submitted or expired."""
    status = await submit.status_of(broker, job_id)
    if status is None:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "no such job"})
    return status


ClientDep = Annotated[ClientInfo, Depends(client_info)]
JobStatusDep = Annotated[dict[str, str], Depends(existing_job)]
