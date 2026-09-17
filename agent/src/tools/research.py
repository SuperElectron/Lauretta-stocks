"""Tools the chat assistant uses to run the research team and read what it saved."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool, tool
from psycopg_pool import AsyncConnectionPool

from src.db.queries import theses
from src.tools.models import TickerArgs

RunResearch = Callable[[str], Awaitable[dict[str, Any]]]


def build_research_stock(run_research: RunResearch) -> BaseTool:
    @tool(args_schema=TickerArgs)
    async def research_stock(ticker: str) -> dict[str, Any]:
        """Run the research team on one company: the analyst writes a stock story, the
        checker re-verifies it, and the advisor weighs it against the investor's portfolio
        and rules. Takes a minute or two and the result is saved. Use it when they ask what to
        do about a stock and there is no recent thesis, or they ask for a fresh look.
        """
        final = await run_research(ticker.upper())
        return {
            "ticker": final["ticker"],
            "thesis_id": final["thesis_id"],
            "revisions": final["revisions"],
            "story": final["story"],
            "review": {k: final["review"][k] for k in ("verdict", "summary", "weaknesses")},
            "advice": final["advice"],
        }

    return research_stock


def build_get_thesis(pool: AsyncConnectionPool, user_id: str) -> BaseTool:
    @tool(args_schema=TickerArgs)
    async def get_thesis(ticker: str) -> dict[str, Any]:
        """The latest saved research on a ticker: story, review and advice, with its date.
        Check the date; prices and news move on.
        """
        saved = await theses.latest(pool, user_id, ticker)
        return {"found": False} if saved is None else {"found": True, **saved}

    return get_thesis
