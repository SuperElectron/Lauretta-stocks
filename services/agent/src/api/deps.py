"""What routes take from the app's state and from the request's forwarded headers.

Who a request acts for is the `X-Lauretta-User` header, which the gateway sets from the verified
caller (its API key, or for AnythingLLM the workspace's model) after removing any client copy.
Only the gateway reaches this API (compose networks). A user outside ALLOWED_USERS, a missing
header or a repeated one is 401; nothing in a request body ever names a user.
"""

import re
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

from src.prompts import errors as wording
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


USER_HEADER = "x-lauretta-user"
# Set by the gateway beside the user: `owner` (the owner's API key) or `anythingllm`.
CALLER_HEADER = "x-lauretta-caller"


def user_of(request: Request) -> str | None:
    """The allowed user the gateway named, or None."""
    named = request.headers.getlist(USER_HEADER)
    if len(named) != 1 or named[0] not in _settings(request).allowed_users():
        return None
    return named[0]


def current_user(request: Request) -> str:
    """The user this request acts for, or 401. Everything keyed per user goes through here."""
    user = user_of(request)
    if user is None:
        raise HTTPException(401, detail={"code": "UNKNOWN_USER", "message": wording.UNKNOWN_USER})
    return user


UserDep = Annotated[str, Depends(current_user)]


async def existing_job(job_id: JobId, broker: BrokerDep, user: UserDep) -> dict[str, str]:
    """The caller's job's status hash. A job never submitted, expired or someone else's is the
    same 404, so a job id tells nobody else anything."""
    status = await submit.status_of(broker, job_id)
    if status is None or status.get("user") != user:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": wording.NO_SUCH_JOB})
    return status


ClientDep = Annotated[ClientInfo, Depends(client_info)]
JobStatusDep = Annotated[dict[str, str], Depends(existing_job)]
