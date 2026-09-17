"""Saved research runs: the story, its review and the advice, per ticker."""

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def save(
    pool: AsyncConnectionPool,
    user_id: str,
    ticker: str,
    story: dict[str, Any],
    review: dict[str, Any],
    advice: dict[str, Any],
    revisions: int,
) -> str:
    (saved,) = await rows(
        pool,
        user_id,
        """INSERT INTO theses (user_id, ticker, story, review, advice, revisions)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id::text""",
        (user_id, ticker.upper(), Jsonb(story), Jsonb(review), Jsonb(advice), revisions),
    )
    return saved["id"]


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


async def recent(pool: AsyncConnectionPool, user_id: str, limit: int) -> list[dict[str, Any]]:
    """The newest thesis per ticker: its date, action and verdict, newest first."""
    return await rows(
        pool,
        user_id,
        """SELECT * FROM (
             SELECT DISTINCT ON (ticker) ticker, created_at::date::text AS created,
                    advice->>'action' AS action, review->>'verdict' AS verdict, created_at
             FROM theses WHERE user_id = %s ORDER BY ticker, created_at DESC
           ) newest ORDER BY created_at DESC LIMIT %s""",
        (user_id, limit),
    )
