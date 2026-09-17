"""Conversations: who owns each, and the aliases (hashes of a prompt and its answer) that find
one again. A thread is keyed by its owner and its id, so two users' threads never collide."""

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def create(pool: AsyncConnectionPool, user_id: str, thread_id: str, client: str) -> bool:
    """Records the thread as `user_id`'s; False when they already have it."""
    created = await rows(
        pool,
        user_id,
        """INSERT INTO threads (user_id, thread_id, client) VALUES (%s, %s, %s)
           ON CONFLICT (user_id, thread_id) DO NOTHING RETURNING thread_id""",
        (user_id, thread_id, client),
    )
    return bool(created)


async def find_aliases(
    pool: AsyncConnectionPool, user_id: str, alias_hashes: list[str]
) -> dict[str, str]:
    """The thread of each alias found among `alias_hashes`, by alias."""
    found = await rows(
        pool,
        user_id,
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
        user_id,
        """INSERT INTO thread_aliases (user_id, alias_hash, thread_id)
           SELECT %s, unnest(%s::text[]), %s
           ON CONFLICT (user_id, alias_hash) DO NOTHING""",
        (user_id, alias_hashes, thread_id),
    )
