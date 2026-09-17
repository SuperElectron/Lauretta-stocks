"""Tools over the investor's holdings, valued at live prices."""

from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from src.data import market
from src.db.queries import holdings
from src.errors import UpstreamUnavailable
from src.graph.ctx import Ctx, user_of
from src.prompts import tools as wording
from src.tools.market import unavailable
from src.tools.scoped import ScopedSetHoldingArgs, ScopedTickerArgs


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
        "note": wording.MIXED_CURRENCIES,
    }


def build_get_portfolio(pool: AsyncConnectionPool) -> BaseTool:
    @tool
    async def get_portfolio(runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """The investor's holdings as they told us, valued at the latest price, with each
        position's weight of the total. Holdings they have not told us about are not here.
        """
        positions = await holdings.all_of(pool, user_of(runtime.context))
        if not positions:
            return {"positions": [], "total_value": 0, "note": wording.NO_HOLDINGS}
        try:
            prices = await market.prices([p["ticker"] for p in positions])
        except UpstreamUnavailable as exc:
            return {"positions": positions, **unavailable(exc)}
        return valued(positions, prices)

    return get_portfolio


def build_set_holding(pool: AsyncConnectionPool) -> BaseTool:
    @tool(args_schema=ScopedSetHoldingArgs)
    async def set_holding(
        ticker: str,
        shares: float,
        runtime: ToolRuntime[Ctx],
        avg_cost: float | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Record a position as the investor now holds it: pass the new total share count,
        not the change. Average cost and note are kept unless you pass new ones.
        """
        await holdings.upsert(pool, user_of(runtime.context), ticker, shares, avg_cost, note)
        return {"saved": True, "ticker": ticker.upper(), "shares": shares}

    return set_holding


def build_remove_holding(pool: AsyncConnectionPool) -> BaseTool:
    @tool(args_schema=ScopedTickerArgs)
    async def remove_holding(ticker: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """Remove a position the investor has fully sold."""
        return {"removed": await holdings.remove(pool, user_of(runtime.context), ticker)}

    return remove_holding
