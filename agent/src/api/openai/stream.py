"""A job's events as an OpenAI answer: streamed as `chat.completion.chunk`s, or waited for.

A stream opens with the role delta (and `WAITING` when the turn is queued behind another),
sends `KEEPALIVE` every `KEEPALIVE_SECONDS` while the job is quiet, and always ends with
`data: [DONE]`: after `done` or `error`, after `limit_s` with the still-working note, or with
`JOB_LOST` when the job's records are gone before it finished. Before the closing chunk the
whole answer text is handed to `Turn.answered`, so the client's next request finds its thread.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from src.api.openai.chunks import KEEPALIVE, ROLE, WAITING, Part, State, map_event
from src.api.openai.models import OpenAIError
from src.queue import events

KEEPALIVE_SECONDS = 15.0
DONE_FRAME = "data: [DONE]\n\n"
LOST = {"code": "JOB_LOST", "message": "its record expired before it finished; ask again"}
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
    # Called with the answer text sent, and whether the job finished `done`.
    answered: Callable[[str, bool], Awaitable[None]]


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


async def _parts(broker: Redis, turn: Turn, limit_s: float) -> AsyncIterator[Part]:
    """Every part of the answer after the role delta, keep-alives included."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
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
            await turn.answered(sent, event.type == "done")
        for part in parts:
            yield part
        if state.finished:
            return
    closing = ("timeout", {}) if loop.time() >= deadline else ("error", LOST)
    parts = map_event(state, *closing)[0]
    await turn.answered(sent + "".join(p.delta.get("content", "") for p in parts), False)
    for part in parts:
        yield part


async def stream(broker: Redis, turn: Turn, limit_s: float) -> AsyncIterator[str]:
    yield frame(turn.meta, ROLE)
    async for part in _parts(broker, turn, limit_s):
        yield frame(turn.meta, part)
    yield DONE_FRAME


async def wait(broker: Redis, turn: Turn, limit_s: float) -> dict[str, Any]:
    """The whole answer if the job finishes within `limit_s`, else the still-working note."""
    content: list[str] = []
    reasoning: list[str] = []
    async for part in _parts(broker, turn, limit_s):
        if part.error is not None:
            message, code = part.error["message"], part.error["code"]
            raise OpenAIError(500, message, code, kind="server_error", headers=NO_RETRY)
        content.append(part.delta.get("content", ""))
        reasoning.append(part.delta.get("reasoning_content", ""))
    message = {"role": "assistant", "content": "".join(content).strip()}
    if "".join(reasoning):
        message["reasoning_content"] = "".join(reasoning)
    return {
        "id": turn.meta.completion_id,
        "object": "chat.completion",
        "created": turn.meta.created,
        "model": turn.meta.model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
