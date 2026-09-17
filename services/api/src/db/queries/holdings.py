"""The investor's holdings, as they told us."""

from decimal import Decimal
from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def all_of(pool: AsyncConnectionPool, user_id: str) -> list[dict[str, Any]]:
    found = await rows(
        pool,
        user_id,
        """SELECT ticker, shares, avg_cost, note, updated_at::date::text AS updated
           FROM holdings WHERE user_id = %s ORDER BY ticker""",
        (user_id,),
    )
    return [{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in found]
