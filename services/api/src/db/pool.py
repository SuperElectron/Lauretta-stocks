"""The API's Postgres pool, and the per-user scope every query on user data runs in.

The app connects as `lauretta_app`, which row-level security applies to: `facts`, `holdings`,
`theses`, `threads` and `thread_aliases` show and accept only rows whose `user_id` is the
transaction's `app.user_id`. The pool is autocommit, so the setting lives only inside an explicit
transaction (`scoped`): a query outside one sees no rows at all, and a connection goes back to the
pool with nothing set. Queries keep their own `WHERE user_id = %s` too.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.errors import DatabaseUnavailable, NoUser

OPEN_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def open_pool(
    database_url: str, *, min_size: int, max_size: int
) -> AsyncGenerator[AsyncConnectionPool]:
    """Opens the pool, yields it, and closes it on exit.

    `autocommit` keeps the user scope inside explicit transactions; rows come back as dicts.
    """
    pool = AsyncConnectionPool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    try:
        await pool.open(wait=True, timeout=OPEN_TIMEOUT_SECONDS)
    except Exception as exc:
        await pool.close()
        raise DatabaseUnavailable from exc

    try:
        yield pool
    finally:
        await pool.close()


_SCOPE = "SELECT set_config('app.user_id', %s, true)"


@asynccontextmanager
async def scoped(pool: AsyncConnectionPool, user_id: str) -> AsyncIterator[AsyncConnection]:
    """A connection in a transaction that sees and writes only `user_id`'s rows."""
    if not user_id:
        raise NoUser
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(_SCOPE, (user_id,))
        yield conn


async def rows(
    pool: AsyncConnectionPool, user_id: str, sql: str, params: tuple | dict = ()
) -> list[dict]:
    """Runs one statement in `user_id`'s scope and returns its rows."""
    async with scoped(pool, user_id) as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        return await cur.fetchall() if cur.description else []


async def ping(pool: AsyncConnectionPool) -> None:
    """The database answers; reads no user data."""
    async with pool.connection() as conn:
        await conn.execute("SELECT 1")
