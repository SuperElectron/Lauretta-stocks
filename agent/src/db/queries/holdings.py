"""The investor's holdings, as they told us."""

from decimal import Decimal
from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def upsert(
    pool: AsyncConnectionPool,
    user_id: str,
    ticker: str,
    shares: float,
    avg_cost: float | None,
    note: str | None,
) -> None:
    """Sets the share count; cost and note are kept unless new ones are given."""
    await rows(
        pool,
        """INSERT INTO holdings (user_id, ticker, shares, avg_cost, note)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (user_id, ticker) DO UPDATE
           SET shares = EXCLUDED.shares,
               avg_cost = COALESCE(EXCLUDED.avg_cost, holdings.avg_cost),
               note = COALESCE(EXCLUDED.note, holdings.note), updated_at = now()""",
        (user_id, ticker.upper(), shares, avg_cost, note),
    )


async def remove(pool: AsyncConnectionPool, user_id: str, ticker: str) -> bool:
    deleted = await rows(
        pool,
        "DELETE FROM holdings WHERE user_id = %s AND ticker = %s RETURNING ticker",
        (user_id, ticker.upper()),
    )
    return bool(deleted)


async def all_of(pool: AsyncConnectionPool, user_id: str) -> list[dict[str, Any]]:
    found = await rows(
        pool,
        """SELECT ticker, shares, avg_cost, note, updated_at::date::text AS updated
           FROM holdings WHERE user_id = %s ORDER BY ticker""",
        (user_id,),
    )
    return [{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in found]
