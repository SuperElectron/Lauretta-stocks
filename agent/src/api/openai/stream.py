"""A job's events as an OpenAI answer: streamed as `chat.completion.chunk`s, or waited for.

A stream opens with the role delta (and `WAITING` when the turn is queued behind another),
sends `KEEPALIVE` every `KEEPALIVE_SECONDS` while the job is quiet, and always ends with
`data: [DONE]`: after `done` or `error`, after `limit_s` with the still-working note, or with
`JOB_LOST` when the job's records are gone before it finished. After the last byte the whole
answer text is handed to `Turn.answered`, so the client's next request finds its thread.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse
from loguru import logger
from redis.asyncio import Redis
from starlette.background import BackgroundTask

from src.api.openai.chunks import KEEPALIVE, ROLE, WAITING, Part, State, map_event
from src.api.openai.models import OpenAIError
from src.queue import events, keys

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


@dataclass
class Outcome:
    """What the client was sent, filled in as the answer ends."""

    text: str = ""
    done: bool = False
    ended: bool = False


async def settle(turn: Turn, outcome: Outcome) -> None:
    """Hands the finished answer to `Turn.answered`, after the client has it all. A failure is
    logged, not raised into a complete answer: it only costs the alias that finds the thread
    on the next turn, and that request falls back to its first-message thread and registers
    every pair it resends."""
    if not outcome.ended:
        return
    try:
        await turn.answered(outcome.text, outcome.done)
    except Exception:
        logger.bind(job_id=turn.job_id).exception("openai.answer_not_recorded")


async def _parts(
    broker: Redis, turn: Turn, limit_s: float, outcome: Outcome
) -> AsyncIterator[Part]:
    """Every part of the answer after the role delta, keep-alives included."""
    deadline = asyncio.get_running_loop().time() + limit_s
    state = State()
    if turn.behind:
        yield WAITING
    read = events.read(broker, turn.job_id, deadline=deadline)
    async for event in _with_keepalive(read, KEEPALIVE_SECONDS):
        if event is None:
            yield KEEPALIVE
            continue
        parts, state = map_event(state, event.type, json.loads(event.data))
        outcome.text += "".join(part.delta.get("content", "") for part in parts)
        outcome.done, outcome.ended = event.type == "done", state.finished
        for part in parts:
            yield part
        if state.finished:
            return
    # The read ended without an outcome: at the deadline, or because the job's records are gone.
    gone = not await broker.exists(keys.job(turn.job_id))
    parts = map_event(state, *(("error", LOST) if gone else ("timeout", {})))[0]
    outcome.text += "".join(part.delta.get("content", "") for part in parts)
    outcome.ended = True
    for part in parts:
        yield part


async def stream(broker: Redis, turn: Turn, limit_s: float) -> AsyncIterator[str]:
    outcome = Outcome()
    yield frame(turn.meta, ROLE)
    async for part in _parts(broker, turn, limit_s, outcome):
        yield frame(turn.meta, part)
    yield DONE_FRAME
    await settle(turn, outcome)


async def wait(broker: Redis, turn: Turn, limit_s: float) -> JSONResponse:
    """The whole answer if the job finishes within `limit_s`, else the still-working note."""
    outcome = Outcome()
    content: list[str] = []
    reasoning: list[str] = []
    async for part in _parts(broker, turn, limit_s, outcome):
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
    return JSONResponse(body, background=BackgroundTask(settle, turn, outcome))
