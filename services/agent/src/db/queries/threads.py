"""Conversations started through the OpenAI-compatible API: who owns each, and the aliases
(hashes of a prompt and its answer) that find one again."""

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def create(pool: AsyncConnectionPool, thread_id: str, user_id: str, client: str) -> bool:
    """Records the thread as `user_id`'s; False when it already exists."""
    created = await rows(
        pool,
        """INSERT INTO threads (thread_id, user_id, client) VALUES (%s, %s, %s)
           ON CONFLICT (thread_id) DO NOTHING RETURNING thread_id""",
        (thread_id, user_id, client),
    )
    return bool(created)


async def owner(pool: AsyncConnectionPool, thread_id: str) -> str | None:
    found = await rows(pool, "SELECT user_id FROM threads WHERE thread_id = %s", (thread_id,))
    return found[0]["user_id"] if found else None


async def find_aliases(
    pool: AsyncConnectionPool, user_id: str, alias_hashes: list[str]
) -> dict[str, str]:
    """The thread of each alias found among `alias_hashes`, by alias."""
    found = await rows(
        pool,
        """SELECT alias_hash, thread_id FROM thread_aliases
           WHERE alias_hash = ANY(%s) AND user_id = %s""",
        (alias_hashes, user_id),
    )
    return {row["alias_hash"]: row["thread_id"] for row in found}


async def add_aliases(
    pool: AsyncConnectionPool, user_id: str, thread_id: str, alias_hashes: list[str]
) -> None:
    """An alias already pointing elsewhere keeps its thread."""
    if not alias_hashes:
        return
    await rows(
        pool,
        """INSERT INTO thread_aliases (alias_hash, thread_id, user_id)
           SELECT unnest(%s::text[]), %s, %s
           ON CONFLICT (alias_hash) DO NOTHING""",
        (alias_hashes, thread_id, user_id),
    )
