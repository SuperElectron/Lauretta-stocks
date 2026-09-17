"""The LangGraph checkpointer: the chat's conversation history, kept across sessions.

Its tables have no user column, so row-level security cannot guard them. Checkpoints are keyed
`{user}:{thread}` by the server (`queue/keys.thread`), and no route reads them directly.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.errors import DatabaseUnavailable


async def build_checkpointer(
    pool: AsyncConnectionPool, owner_url: str | None = None
) -> AsyncPostgresSaver:
    """Creates the checkpoint tables if they are missing, then returns the saver over the pool.

    The app role may not create tables, so `owner_url` (the owner role) runs the setup on a
    connection of its own, closed at once; without it the pool's role runs it.
    """
    try:
        if owner_url is None:
            await AsyncPostgresSaver(conn=pool).setup()
        else:
            async with await AsyncConnection.connect(
                owner_url, autocommit=True, row_factory=dict_row
            ) as conn:
                await AsyncPostgresSaver(conn=conn).setup()
    except Exception as exc:
        raise DatabaseUnavailable from exc
    return AsyncPostgresSaver(conn=pool)
