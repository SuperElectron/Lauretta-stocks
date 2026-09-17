"""The LangGraph checkpointer: the chat's conversation history, kept across sessions.

Its tables have no user column, so row-level security cannot guard them. Checkpoints are keyed
`{user}:{thread}` by the server (`queue/keys.thread`), and no route reads them directly.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.errors import DatabaseUnavailable


async def create_tables(setup_url: str) -> None:
    """Creates the checkpoint tables if they are missing, on a connection of its own.

    `setup_url` is `lauretta_migrator` in the stack: the app role may not create tables.
    """
    try:
        async with await AsyncConnection.connect(
            setup_url, autocommit=True, row_factory=dict_row
        ) as conn:
            await AsyncPostgresSaver(conn=conn).setup()
    except Exception as exc:
        raise DatabaseUnavailable from exc


async def build_checkpointer(
    pool: AsyncConnectionPool, setup_url: str | None = None
) -> AsyncPostgresSaver:
    """The saver over the pool, once its tables exist (created as `setup_url`, if given, else
    as the pool's role)."""
    if setup_url is not None:
        await create_tables(setup_url)
    else:
        try:
            await AsyncPostgresSaver(conn=pool).setup()
        except Exception as exc:
            raise DatabaseUnavailable from exc
    return AsyncPostgresSaver(conn=pool)
