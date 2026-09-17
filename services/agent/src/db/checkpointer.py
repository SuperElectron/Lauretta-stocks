"""The LangGraph checkpointer: the chat's conversation history, kept across sessions.

Its tables have no user column, so row-level security cannot guard them. Checkpoints are keyed
`{user}:{thread}` by the server (`queue/keys.thread`), and no route reads them directly.

The tables are created by a deploy step (`python -m src.db.migrate`, the compose `migrate`
service) as `lauretta_migrator`; the long-running worker only checks they are current, so it
never holds a role that may create tables.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.errors import DatabaseUnavailable

CHECKPOINTS_NOT_MIGRATED = (
    "the checkpoint tables are missing or out of date; on the Spark run "
    "`docker compose run --rm migrate`, locally `just migrate` or set DATABASE_SETUP_URL"
)

_VERSION = "SELECT max(v) AS v FROM checkpoint_migrations"


async def create_tables(setup_url: str) -> None:
    """Creates or migrates the checkpoint tables, on a connection of its own."""
    try:
        async with await AsyncConnection.connect(
            setup_url, autocommit=True, row_factory=dict_row
        ) as conn:
            await AsyncPostgresSaver(conn=conn).setup()
    except Exception as exc:
        raise DatabaseUnavailable from exc


async def check_tables(pool: AsyncConnectionPool) -> None:
    """`DatabaseUnavailable` unless the checkpoint tables exist at the latest migration."""
    latest = len(AsyncPostgresSaver.MIGRATIONS) - 1
    try:
        async with pool.connection() as conn:
            found = await (await conn.execute(_VERSION)).fetchone()
    except Exception as exc:
        raise DatabaseUnavailable(CHECKPOINTS_NOT_MIGRATED) from exc
    if found is None or found["v"] != latest:
        raise DatabaseUnavailable(CHECKPOINTS_NOT_MIGRATED)


async def build_checkpointer(
    pool: AsyncConnectionPool, setup_url: str | None = None
) -> AsyncPostgresSaver:
    """The saver over the pool. With `setup_url` (local development) the tables are created
    first; otherwise they must already be current."""
    if setup_url is not None:
        await create_tables(setup_url)
    else:
        await check_tables(pool)
    return AsyncPostgresSaver(conn=pool)
