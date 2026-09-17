"""Which thread an OpenAI-style request continues. Chat apps send history, never an id.

- `X-Thread-Id`, when sent, names the thread (hashed with the user).
- A request with no history is a new conversation: it takes its first-message thread, or a
  fresh one when that thread is already in use (two conversations that both open "hi").
- A request with history follows the alias of the oldest prompt and answer it still carries,
  else its first-message thread. Each answered pair it carries is registered as an alias, and
  each answer is registered as it is sent, so turn two already finds a fresh thread.
"""

import secrets

from loguru import logger
from psycopg_pool import AsyncConnectionPool

from src.api.openai import digests
from src.api.openai.models import ChatRequest, OpenAIError
from src.db.queries import threads


async def _owned(pool: AsyncConnectionPool, thread_id: str, user_id: str, client: str) -> str:
    """The thread, recorded as the user's if new; someone else's thread is not found."""
    if await threads.create(pool, thread_id, user_id, client):
        return thread_id
    if await threads.owner(pool, thread_id) != user_id:
        logger.bind(thread_id=thread_id).warning("openai.thread_not_owned")
        raise OpenAIError(404, "no such conversation", "thread_not_found")
    return thread_id


async def resolve(
    pool: AsyncConnectionPool, user_id: str, request: ChatRequest, header: str | None, client: str
) -> str:
    if header is not None:
        return await _owned(pool, digests.header_thread(user_id, header), user_id, client)
    base = digests.first_message_thread(user_id, request)
    pairs = request.pairs()
    if not pairs:
        if await threads.create(pool, base, user_id, client):
            return base
        fresh = f"{base}-{secrets.token_hex(6)}"
        logger.bind(thread_id=fresh).info("openai.thread_forked")
        return await _owned(pool, fresh, user_id, client)
    aliases = [digests.pair_alias(user_id, prompt, answer) for prompt, answer in pairs]
    found = await threads.find_alias(pool, user_id, aliases[0])
    thread_id = await _owned(pool, found or base, user_id, client)
    await threads.add_aliases(pool, user_id, thread_id, aliases)
    return thread_id


async def remember_answer(
    pool: AsyncConnectionPool, user_id: str, thread_id: str, prompt: str, answer: str
) -> None:
    """Registers the answer just sent, which the client will resend with its prompt."""
    if digests.answer_text(answer):
        alias = digests.pair_alias(user_id, prompt, answer)
        await threads.add_aliases(pool, user_id, thread_id, [alias])
