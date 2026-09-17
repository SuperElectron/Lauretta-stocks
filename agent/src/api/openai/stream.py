"""A job's events as an OpenAI answer: streamed as `chat.completion.chunk`s, or waited for.

A stream opens with the role delta before any event, sends `KEEPALIVE` every
`KEEPALIVE_SECONDS` while the job is quiet, and always ends with `data: [DONE]`: after `done`
or `error`, after `limit_s` with the timeout note, or with `JOB_LOST` when the job's
records are gone before it finished.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from src.api.openai.chunks import KEEPALIVE, ROLE, TIMED_OUT, Part, State, map_event
from src.api.openai.models import OpenAIError
from src.queue import events

KEEPALIVE_SECONDS = 15.0
DONE_FRAME = "data: [DONE]\n\n"
LOST = {"code": "JOB_LOST", "message": "its record expired before it finished; ask again"}
STILL_WORKING = (
    "The court is still at work on this. Ask again in a minute and the answer will be ready."
)


@dataclass(frozen=True)
class Meta:
    completion_id: str
    model: str
    created: int


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


async def _parts(broker: Redis, job_id: str, limit_s: float) -> AsyncIterator[Part]:
    """Every part of the answer after the role delta, keep-alives included."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
    state = State()
    read = events.read(broker, job_id, deadline=deadline)
    async for event in _with_keepalive(read, KEEPALIVE_SECONDS):
        if event is None:
            yield KEEPALIVE
            continue
        parts, state = map_event(state, event.type, json.loads(event.data))
        for part in parts:
            yield part
        if state.finished:
            return
    closing = ("timeout", {}) if loop.time() >= deadline else ("error", LOST)
    for part in map_event(state, *closing)[0]:
        yield part


async def stream(broker: Redis, job_id: str, meta: Meta, limit_s: float) -> AsyncIterator[str]:
    yield frame(meta, ROLE)
    async for part in _parts(broker, job_id, limit_s):
        yield frame(meta, part)
    yield DONE_FRAME


async def wait(broker: Redis, job_id: str, meta: Meta, limit_s: float) -> dict[str, Any]:
    """The whole answer if the job finishes within `limit_s`, else a note to ask again."""
    content: list[str] = []
    reasoning: list[str] = []
    async for part in _parts(broker, job_id, limit_s):
        if part.error is not None:
            raise OpenAIError(500, part.error["message"], part.error["code"], kind="server_error")
        if part.delta.get("content") == TIMED_OUT:
            content = [STILL_WORKING]
            break
        content.append(part.delta.get("content", ""))
        reasoning.append(part.delta.get("reasoning_content", ""))
    message = {"role": "assistant", "content": "".join(content).strip()}
    if "".join(reasoning):
        message["reasoning_content"] = "".join(reasoning)
    return {
        "id": meta.completion_id,
        "object": "chat.completion",
        "created": meta.created,
        "model": meta.model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
