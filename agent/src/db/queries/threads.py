"""Who owns each conversation started through the OpenAI-compatible API."""

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def claim(pool: AsyncConnectionPool, thread_id: str, user_id: str, client: str) -> str:
    """Records the thread as `user_id`'s unless it exists, and returns its owner.

    The no-op update makes the row come back either way, even when another request inserts it
    concurrently (a `DO NOTHING` then a read could miss that row).
    """
    (owner,) = await rows(
        pool,
        """INSERT INTO threads (thread_id, user_id, client) VALUES (%s, %s, %s)
           ON CONFLICT (thread_id) DO UPDATE SET thread_id = EXCLUDED.thread_id
           RETURNING user_id""",
        (thread_id, user_id, client),
    )
    return owner["user_id"]
