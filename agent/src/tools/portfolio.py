"""Tools over the investor's holdings, valued at live prices."""

from typing import Any

from langchain_core.tools import BaseTool, tool
from psycopg_pool import AsyncConnectionPool

from src.data import market
from src.db.queries import holdings
from src.errors import UpstreamUnavailable
from src.tools.market import unavailable
from src.tools.models import SetHoldingArgs, TickerArgs


def valued(positions: list[dict[str, Any]], prices: dict[str, float | None]) -> dict[str, Any]:
    """Each position's value and weight among the priced positions."""
    rows = []
    for position in positions:
        price = prices.get(position["ticker"])
        value = round(price * position["shares"], 2) if price else None
        rows.append({**position, "price": price, "value": value})
    total = sum(row["value"] for row in rows if row["value"] is not None)
    for row in rows:
        priced = row["value"] is not None and total
        row["weight_pct"] = round(row["value"] / total * 100, 1) if priced else None
    return {
        "positions": sorted(rows, key=lambda row: row["value"] or 0, reverse=True),
        "total_value": round(total, 2),
        "unpriced": [row["ticker"] for row in rows if row["value"] is None],
        "note": "Values are in each listing's own currency; weights assume one currency.",
    }


def build_get_portfolio(pool: AsyncConnectionPool, user_id: str) -> BaseTool:
    @tool
    async def get_portfolio() -> dict[str, Any]:
        """The investor's holdings as they told us, valued at the latest price, with each
        position's weight of the total. Holdings they have not told us about are not here.
        """
        positions = await holdings.all_of(pool, user_id)
        if not positions:
            return {"positions": [], "total_value": 0, "note": "No holdings recorded yet."}
        try:
            prices = await market.prices([p["ticker"] for p in positions])
        except UpstreamUnavailable as exc:
            return {"positions": positions, **unavailable(exc)}
        return valued(positions, prices)

    return get_portfolio


def build_set_holding(pool: AsyncConnectionPool, user_id: str) -> BaseTool:
    @tool(args_schema=SetHoldingArgs)
    async def set_holding(
        ticker: str, shares: float, avg_cost: float | None = None, note: str | None = None
    ) -> dict[str, Any]:
        """Record a position as the investor now holds it: pass the new total share count,
        not the change. Average cost and note are kept unless you pass new ones.
        """
        await holdings.upsert(pool, user_id, ticker, shares, avg_cost, note)
        return {"saved": True, "ticker": ticker.upper(), "shares": shares}

    return set_holding


def build_remove_holding(pool: AsyncConnectionPool, user_id: str) -> BaseTool:
    @tool(args_schema=TickerArgs)
    async def remove_holding(ticker: str) -> dict[str, Any]:
        """Remove a position the investor has fully sold."""
        return {"removed": await holdings.remove(pool, user_id, ticker)}

    return remove_holding
