"""The LangGraph checkpointer: the chat's conversation history, kept across sessions."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from src.errors import DatabaseUnavailable


async def build_checkpointer(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
    """Creates the checkpoint tables if they are missing, then returns the saver over the pool."""
    saver = AsyncPostgresSaver(conn=pool)
    try:
        await saver.setup()
    except Exception as exc:
        raise DatabaseUnavailable from exc
    return saver
