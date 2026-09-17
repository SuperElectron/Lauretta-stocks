"""`GET /v1/models` and `POST /v1/chat/completions`: the court for OpenAI-compatible chat apps.

A thin adapter over the job queue. Only the last user message enters the graph; the client's
system prompt, retrieved context and resent history are ignored, because the thread's
checkpoint is the conversation. `stream: true` answers with server-sent chunks; otherwise the
request waits up to `API_MAX_WAIT_S`.
"""

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import ValidationError

from src.api.deps import BrokerDep, ClientDep, PoolDep, SettingsDep, UserDep
from src.api.openai import stream, threads
from src.api.openai.models import MODEL, ChatRequest, OpenAIError, chat_request
from src.queue import submit
from src.queue.models import Job

router = APIRouter()
# When the model was first served; OpenAI's model objects carry a creation time.
MODEL_CREATED = 1_788_000_000
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


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
        raise OpenAIError(
            404,
            f"there is no model {request.model!r}; use {MODEL!r}",
            "model_not_found",
            param="model",
        )
    message = request.last_user_text()
    thread_id = threads.thread_id_for(user_id, request, x_thread_id)
    try:
        job = Job(
            kind="chat",
            thread_id=thread_id,
            message=message,
            client=client,
            job_id=threads.job_id_for(user_id, thread_id, request),
        )
    except ValidationError as exc:
        raise OpenAIError(400, "the last message is too long", "message_too_long") from exc
    await threads.claim(pool, thread_id, user_id, client.client)
    queued = await submit.submit_once(broker, job, settings.EVENTS_TTL_S)
    logger.bind(
        job_id=job.job_id, thread_id=thread_id, retry=not queued, ignored=len(request.messages) - 1
    ).info("openai.turn")
    meta = stream.Meta(f"chatcmpl-{job.job_id}", MODEL, int(time.time()))
    if request.stream:
        body = stream.stream(broker, job.job_id, meta, settings.API_MAX_STREAM_S)
        return StreamingResponse(body, media_type="text/event-stream", headers=SSE_HEADERS)
    return JSONResponse(await stream.wait(broker, job.job_id, meta, settings.API_MAX_WAIT_S))
