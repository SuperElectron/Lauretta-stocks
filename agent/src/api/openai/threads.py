"""Which conversation, and which job, an OpenAI-style request belongs to.

Chat clients send the whole visible history and no conversation id, so both are derived:

- The thread is a hash of the user, the model and the first user message: the same
  conversation in the client lands on the same thread every turn. `X-Thread-Id` overrides the
  first message for clients that can name their conversations; it is hashed with the user too,
  so two users' ids never meet.
- The job is a hash of the user, the thread, the last user message and how many user messages
  were sent: a retried request (SDK retries, a reconnect) names the job already queued, while
  the same words sent again as a new turn name a new one.
"""

import hashlib
import re

from loguru import logger
from psycopg_pool import AsyncConnectionPool

from src.api.openai.models import ChatRequest, OpenAIError
from src.db.queries import threads

THREAD_PREFIX = "oa-"
_THREAD_HEADER = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


def _digest(*parts: str) -> str:
    # Length-prefixed, so no two different part lists hash the same bytes.
    joined = "".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


def thread_id_for(user_id: str, request: ChatRequest, header: str | None) -> str:
    if header is not None:
        if not _THREAD_HEADER.fullmatch(header):
            raise OpenAIError(
                400, "X-Thread-Id must be 1-64 letters, digits or _.:-", "invalid_thread_id"
            )
        return THREAD_PREFIX + _digest(user_id, "header", header)
    first = request.user_texts()[0]
    return THREAD_PREFIX + _digest(user_id, "first", request.model, first)


def job_id_for(user_id: str, thread_id: str, request: ChatRequest) -> str:
    """32 hex characters, the shape of every job id."""
    users = request.user_texts()
    return _digest(user_id, thread_id, users[-1], str(len(users)))


async def claim(pool: AsyncConnectionPool, thread_id: str, user_id: str, client: str) -> None:
    """Records a new thread as the user's; a thread someone else started is not found."""
    owner = await threads.claim(pool, thread_id, user_id, client)
    if owner != user_id:
        logger.bind(thread_id=thread_id).warning("openai.thread_not_owned")
        raise OpenAIError(404, "no such conversation", "thread_not_found")
