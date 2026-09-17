"""The agent's single Postgres pool."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.errors import DatabaseUnavailable

OPEN_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def open_pool(
    database_url: str, *, min_size: int, max_size: int
) -> AsyncGenerator[AsyncConnectionPool]:
    """Opens the pool, yields it, and closes it on exit.

    `autocommit` and `dict_row` are what the checkpointer requires of its connections.
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


async def rows(pool: AsyncConnectionPool, sql: str, params: tuple | dict = ()) -> list[dict]:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        return await cur.fetchall() if cur.description else []
