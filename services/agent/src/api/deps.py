"""What routes take from the app's state and from the request's forwarded headers."""

import re
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request
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


# What a client may call itself in the signals it leaves; anything else is stored as unknown.
_CLIENT_NAME = re.compile(r"[A-Za-z0-9._/-]{1,40}")
JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def client_info(request: Request) -> ClientInfo:
    """The app that called, forwarded by the gateway (which authenticates): `X-Client-Name`
    when sent, else `User-Agent`, kept only when it is a short plain name. No IP is kept."""
    name = request.headers.get("x-client-name") or request.headers.get("user-agent") or ""
    return ClientInfo(client=name) if _CLIENT_NAME.fullmatch(name) else ClientInfo()


async def existing_job(job_id: JobId, broker: BrokerDep) -> dict[str, str]:
    """The job's status hash, or 404 for a job never submitted or expired."""
    status = await submit.status_of(broker, job_id)
    if status is None:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "no such job"})
    return status


def current_user(request: Request) -> str:
    """The user this request acts for: `USER_ID` while one investor uses the court.

    Initiative 2 (multi-user identity) replaces this with the `X-Lauretta-User` header the
    gateway sets from the verified caller. Everything keyed per user goes through here.
    """
    return _settings(request).USER_ID


ClientDep = Annotated[ClientInfo, Depends(client_info)]
UserDep = Annotated[str, Depends(current_user)]
JobStatusDep = Annotated[dict[str, str], Depends(existing_job)]
