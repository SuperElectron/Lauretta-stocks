"""`GET /v1/jobs/{id}/events`: a job's events as server-sent events.

Every check runs before the stream opens, so a refusal is a status code. The SSE id is the
event's stream entry id: a reconnecting client sends it back as `Last-Event-ID` and resumes
after it. FastAPI sends `: ping` every 15s while idle and sets `Cache-Control: no-cache` and
`X-Accel-Buffering: no`. The stream ends after `done` or `error`.
"""

from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from src.api.deps import BrokerDep, JobStatusDep
from src.queue import events, keys

router = APIRouter()


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
    job_id: str,
    _job: JobStatusDep,
    broker: BrokerDep,
    after: Annotated[str, Depends(resume_after)],
) -> AsyncIterable[ServerSentEvent]:
    async for event in events.read(broker, job_id, after):
        yield to_sse(event)
