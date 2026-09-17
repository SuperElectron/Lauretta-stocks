"""`GET /v1/models` and `POST /v1/chat/completions`: the court for OpenAI-compatible chat apps.

A thin adapter over the job queue. Only the last user message enters the graph; the client's
system prompt, retrieved context and resent history are ignored, because the thread's
checkpoint is the conversation (the history only finds the thread, see `threads.py`).
An identical request within `REQUEST_TTL_S` attaches to the job it queued, unless that job
failed or its answer was delivered in full: then it is a new turn (a resend, a regenerate).
`stream: true` answers with server-sent chunks; otherwise the request waits up to
`API_MAX_WAIT_S`.
"""

import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import ValidationError

from src.api.deps import BrokerDep, ClientDep, PoolDep, SettingsDep, UserDep
from src.api.openai import digests, stream, threads
from src.api.openai.models import MODEL, ChatRequest, OpenAIError, chat_request
from src.queue import keys, submit
from src.queue.models import Job, JobRequest

router = APIRouter()
# When the model was first served; OpenAI's model objects carry a creation time.
MODEL_CREATED = 1_788_000_000
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
# How long an identical request attaches to the job it queued: SDK retries come within seconds.
REQUEST_TTL_S = 900
_THREAD_HEADER = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


@router.get("/v1/models")
async def list_models() -> dict[str, Any]:
    model = {"id": MODEL, "object": "model", "created": MODEL_CREATED, "owned_by": "lauretta"}
    return {"object": "list", "data": [model]}


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Annotated[ChatRequest, Depends(chat_request)],
    user_id: UserDep,
    client: ClientDep,
    broker: BrokerDep,
    pool: PoolDep,
    settings: SettingsDep,
    x_thread_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse | JSONResponse:
    if request.model != MODEL:
        raise OpenAIError(404, f"no such model; use {MODEL!r}", "model_not_found", param="model")
    message = request.last_user_text()
    # A conversation that opens without text would share its thread with every other such one.
    request.first_user_text()
    if x_thread_id is not None and not _THREAD_HEADER.fullmatch(x_thread_id):
        raise OpenAIError(
            400, "X-Thread-Id must be 1-64 letters, digits or _.:-", "invalid_thread_id"
        )
    try:
        JobRequest(kind="chat", message=message)
    except ValidationError as exc:
        raise OpenAIError(400, "the last message is too long", "message_too_long") from exc
    request_key = keys.request(digests.request_key(user_id, request, x_thread_id))
    queued = await submit.attachable(broker, request_key)
    if queued is None:
        thread_id = await threads.resolve(pool, user_id, request, x_thread_id, client.client)
        job = Job(kind="chat", thread_id=thread_id, message=message, client=client)
        queued = await submit.submit_once(
            broker, job, settings.EVENTS_TTL_S, request_key, REQUEST_TTL_S
        )
    logger.bind(
        job_id=queued.job_id,
        thread_id=queued.thread_id,
        attached=queued.attached,
        behind=queued.behind,
        ignored=len(request.messages) - 1,
    ).info("openai.turn")

    async def answered(text: str, done: bool) -> None:
        await threads.remember_answer(pool, user_id, queued.thread_id, message, text)
        if done:
            await submit.release(broker, request_key, queued.job_id)

    meta = stream.Meta(f"chatcmpl-{queued.job_id}", MODEL, int(time.time()))
    turn = stream.Turn(queued.job_id, meta, queued.behind, answered)
    if request.stream:
        body = stream.stream(broker, turn, settings.API_MAX_STREAM_S)
        return StreamingResponse(body, media_type="text/event-stream", headers=SSE_HEADERS)
    return await stream.wait(broker, turn, settings.API_MAX_WAIT_S)
