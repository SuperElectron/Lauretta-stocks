"""Which thread an OpenAI-style request continues. Chat apps send history, never an id.

Threads are keyed by user and id (`threads` table, row-level security), so a thread id names
a conversation of the caller's alone; nobody reaches another user's thread by naming its id.

- `X-Thread-Id`, when sent, names the thread (hashed with the user).
- A request with no history is a new conversation: it takes its first-message thread, or a
  fresh one when that thread is already in use (two conversations that both open "hi").
- A request with history follows the alias of the oldest prompt and answer it still carries
  that is known, else its first-message thread. Each answered pair it carries is registered
  as an alias, and each answer once it is sent, so turn two already finds a fresh thread.
"""

import secrets

from loguru import logger
from psycopg_pool import AsyncConnectionPool

from src.api.openai import digests
from src.api.openai.models import ChatRequest
from src.db.queries import threads
from src.prompts.notes import TIMED_OUT, WAITING

FIXED_NOTES = frozenset(digests.answer_text(note) for note in (TIMED_OUT, WAITING))


async def _owned(pool: AsyncConnectionPool, thread_id: str, user_id: str, client: str) -> str:
    """The user's thread, recorded if new."""
    await threads.create(pool, user_id, thread_id, client)
    return thread_id


async def resolve(
    pool: AsyncConnectionPool, user_id: str, request: ChatRequest, header: str | None, client: str
) -> str:
    if header is not None:
        return await _owned(pool, digests.header_thread(user_id, header), user_id, client)
    base = digests.first_message_thread(user_id, request)
    pairs = request.pairs()
    if not pairs:
        if await threads.create(pool, user_id, base, client):
            return base
        fresh = f"{base}-{secrets.token_hex(6)}"
        logger.bind(thread_id=fresh).info("openai.thread_forked")
        return await _owned(pool, fresh, user_id, client)
    aliases = [digests.pair_alias(user_id, prompt, answer) for prompt, answer in pairs]
    # The oldest pair found wins; any pair found beats the first message, which a forked
    # conversation shares with the one it forked from.
    found = await threads.find_aliases(pool, user_id, aliases)
    known = next((found[alias] for alias in aliases if alias in found), None)
    thread_id = await _owned(pool, known or base, user_id, client)
    await threads.add_aliases(pool, user_id, thread_id, aliases)
    return thread_id


async def remember_answer(
    pool: AsyncConnectionPool, user_id: str, thread_id: str, prompt: str, answer: str
) -> None:
    """Registers the answer just sent, which the client will resend with its prompt. A fixed
    note alone is not: every conversation that hit it would share the alias."""
    text = digests.answer_text(answer)
    if text and text not in FIXED_NOTES:
        alias = digests.pair_alias(user_id, prompt, answer)
        await threads.add_aliases(pool, user_id, thread_id, [alias])
