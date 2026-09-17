"""`GET /v1/jobs/{id}/events`: a job's events as server-sent events.

Every check runs before the stream opens, so a refusal is a status code. The SSE id is the
event's stream entry id: a reconnecting client sends it back as `Last-Event-ID` and resumes
after it. FastAPI sends `: ping` every 15s while idle and sets `Cache-Control: no-cache` and
`X-Accel-Buffering: no`. The stream ends after `done` or `error`; when the job is found finished
or expired with nothing more to send; or after `API_MAX_STREAM_S` with `timeout STREAM_TIMEOUT`
(the job itself carries on, so a client can tell the cap from a failed job).
"""

import asyncio
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from src.api.deps import BrokerDep, JobId, JobStatusDep, SettingsDep
from src.queue import events, keys
from src.queue.models import TERMINAL, Timeout

router = APIRouter()
STREAM_TIMEOUT = Timeout(
    code="STREAM_TIMEOUT",
    message="this stream reached its time limit; the job carries on, reconnect to follow it",
)


def resume_after(last_event_id: Annotated[str | None, Header()] = None) -> str:
    if last_event_id is None:
        return keys.SCAN_START
    if not events.is_entry_id(last_event_id):
        raise HTTPException(400, detail={"code": "BAD_LAST_EVENT_ID", "message": "not an event id"})
    return last_event_id


def to_sse(event: events.StoredEvent) -> ServerSentEvent:
    return ServerSentEvent(raw_data=event.data, event=event.type, id=event.id)


@router.get("/v1/jobs/{job_id}/events", response_class=EventSourceResponse)
async def job_events(
    job_id: JobId,
    _job: JobStatusDep,
    broker: BrokerDep,
    settings: SettingsDep,
    after: Annotated[str, Depends(resume_after)],
) -> AsyncIterable[ServerSentEvent]:
    deadline = asyncio.get_running_loop().time() + settings.API_MAX_STREAM_S
    ended = False
    async for event in events.read(broker, job_id, after, deadline=deadline):
        ended = event.type in TERMINAL
        yield to_sse(event)
    if not ended and asyncio.get_running_loop().time() >= deadline:
        # No id: a client that reconnects resumes after the last real event.
        yield ServerSentEvent(data=STREAM_TIMEOUT.model_dump(), event=STREAM_TIMEOUT.type)
