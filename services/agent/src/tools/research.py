"""Tools the chat assistant uses to put the desk to work and read what it saved."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from src.db.queries import theses
from src.graph.ctx import Ctx, user_of
from src.tools.scoped import ScopedTickerArgs

# Runs the research team on a ticker for the run's user, passed on as the pipeline's context.
RunResearch = Callable[[str, Ctx], Awaitable[dict[str, Any]]]


def build_research_stock(run_research: RunResearch) -> BaseTool:
    @tool(args_schema=ScopedTickerArgs)
    async def research_stock(ticker: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """Put the desk on one company: the Analyst writes a stock story, the Checker re-checks
        every figure, and the Strategist sizes it against the investor's book and rules. The
        result carries each agent's current name in `names`. Takes a minute
        or two and the result is saved. Use it when they ask what to do about a stock and there
        is no recent thesis, or they want a fresh read.
        """
        final = await run_research(ticker.upper(), Ctx(user_id=user_of(runtime.context)))
        return {
            "ticker": final["ticker"],
            "thesis_id": final["thesis_id"],
            "revisions": final["revisions"],
            "story": final["story"],
            "review": {k: final["review"][k] for k in ("verdict", "summary", "weaknesses")},
            "advice": final["advice"],
            "names": final["names"],
        }

    return research_stock


def build_get_thesis(pool: AsyncConnectionPool) -> BaseTool:
    @tool(args_schema=ScopedTickerArgs)
    async def get_thesis(ticker: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """The latest saved research on a ticker: story, review and advice, with its date.
        Check the date; prices and news move on.
        """
        saved = await theses.latest(pool, user_of(runtime.context), ticker)
        return {"found": False} if saved is None else {"found": True, **saved}

    return get_thesis
