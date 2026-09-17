"""Saved research runs: the story, its review and the advice, per ticker."""

from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def latest(pool: AsyncConnectionPool, user_id: str, ticker: str) -> dict[str, Any] | None:
    found = await rows(
        pool,
        user_id,
        """SELECT ticker, story, review, advice, revisions, created_at::date::text AS created
           FROM theses WHERE user_id = %s AND ticker = %s
           ORDER BY created_at DESC LIMIT 1""",
        (user_id, ticker.upper()),
    )
    return found[0] if found else None
