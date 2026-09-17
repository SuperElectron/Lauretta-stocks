"""A job's events as an OpenAI answer: streamed as `chat.completion.chunk`s, or waited for.

A stream opens with the role delta (and `WAITING` when the turn is queued behind another),
sends `KEEPALIVE` every `KEEPALIVE_SECONDS` while the job is quiet, and always ends with
`data: [DONE]`: after `done` or `error`, after `limit_s` with the still-working note, or with
`JOB_LOST` when the job's records are gone before it finished. As the outcome is read, the
answer is recorded in its own task (`settle.py`), so the client's next request finds its thread.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from src.api.openai import settle
from src.api.openai.chunks import KEEPALIVE, ROLE, WAITING, Part, State, map_event
from src.api.openai.models import OpenAIError
from src.prompts import notes
from src.queue import events, keys

KEEPALIVE_SECONDS = 15.0
DONE_FRAME = "data: [DONE]\n\n"
LOST = {"code": "JOB_LOST", "message": notes.JOB_LOST}
# A failed turn is not worth the SDK's automatic retry: it would fail the same way.
NO_RETRY = {"x-should-retry": "false"}


@dataclass(frozen=True)
class Meta:
    completion_id: str
    model: str
    created: int


@dataclass(frozen=True)
class Turn:
    job_id: str
    meta: Meta
    behind: bool
    answered: settle.Answered


def chunk(meta: Meta, part: Part) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": meta.completion_id,
        "object": "chat.completion.chunk",
        "created": meta.created,
        "model": meta.model,
        "choices": [{"index": 0, "delta": part.delta, "finish_reason": part.finish_reason}],
    }
    if part.error is not None:
        body["error"] = part.error
    return body


def frame(meta: Meta, part: Part) -> str:
    return f"data: {json.dumps(chunk(meta, part), ensure_ascii=False)}\n\n"


async def _with_keepalive(
    source: AsyncIterator[events.StoredEvent], interval: float
) -> AsyncIterator[events.StoredEvent | None]:
    """Items from `source`, and None each time `interval` seconds pass without one."""
    end = object()

    async def following() -> Any:
        return await anext(source, end)

    pending = asyncio.create_task(following())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            item = pending.result()
            if item is end:
                return
            yield item
            pending = asyncio.create_task(following())
    finally:
        pending.cancel()


async def _parts(
    broker: Redis, turn: Turn, limit_s: float, recording: list[asyncio.Task[None]]
) -> AsyncIterator[Part]:
    """Every part of the answer after the role delta, keep-alives included. Once the outcome is
    known, before its closing parts are yielded, the answer is recorded (`settle`)."""
    deadline = asyncio.get_running_loop().time() + limit_s
    state, sent = State(), ""
    if turn.behind:
        yield WAITING
    read = events.read(broker, turn.job_id, deadline=deadline)
    async for event in _with_keepalive(read, KEEPALIVE_SECONDS):
        if event is None:
            yield KEEPALIVE
            continue
        parts, state = map_event(state, event.type, json.loads(event.data))
        sent += "".join(part.delta.get("content", "") for part in parts)
        if state.finished:
            recording.append(settle.start(turn.job_id, turn.answered, sent, event.type == "done"))
        for part in parts:
            yield part
        if state.finished:
            return
    # The read ended without an outcome: at the deadline, or because the job's records are gone.
    gone = not await broker.exists(keys.job(turn.job_id))
    parts = map_event(state, *(("error", LOST) if gone else ("timeout", {})))[0]
    sent += "".join(part.delta.get("content", "") for part in parts)
    recording.append(settle.start(turn.job_id, turn.answered, sent, False))
    for part in parts:
        yield part


async def stream(broker: Redis, turn: Turn, limit_s: float) -> AsyncIterator[str]:
    recording: list[asyncio.Task[None]] = []
    yield frame(turn.meta, ROLE)
    async for part in _parts(broker, turn, limit_s, recording):
        yield frame(turn.meta, part)
    yield DONE_FRAME
    await settle.finish(recording)


async def wait(broker: Redis, turn: Turn, limit_s: float) -> JSONResponse:
    """The whole answer if the job finishes within `limit_s`, else the still-working note."""
    content: list[str] = []
    reasoning: list[str] = []
    recording: list[asyncio.Task[None]] = []
    async for part in _parts(broker, turn, limit_s, recording):
        if part.error is not None:
            message, code = part.error["message"], part.error["code"]
            raise OpenAIError(500, message, code, kind="server_error", headers=NO_RETRY)
        content.append(part.delta.get("content", ""))
        reasoning.append(part.delta.get("reasoning_content", ""))
    message = {"role": "assistant", "content": "".join(content).strip()}
    if "".join(reasoning):
        message["reasoning_content"] = "".join(reasoning)
    body = {
        "id": turn.meta.completion_id,
        "object": "chat.completion",
        "created": turn.meta.created,
        "model": turn.meta.model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    await settle.finish(recording)
    return JSONResponse(body)
