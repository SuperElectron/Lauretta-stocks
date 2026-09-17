"""Tools the chat assistant uses to put the desk to work and read what it saved.

Research takes minutes, so `start_research` only starts it: the run goes on after the turn ends,
and the desk reports it in the `<research>` block of a later turn (`graph/research.py`).
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from src.db.queries import theses
from src.graph.ctx import Ctx, user_of
from src.tools.scoped import Scoped, ScopedTickerArgs

if TYPE_CHECKING:
    from src.runs import Runs

# Runs the research team on a ticker for the run's user, passed on as the pipeline's context.
RunResearch = Callable[[str, Ctx], Awaitable[dict[str, Any]]]


def build_start_research(runs: "Runs") -> BaseTool:
    @tool(args_schema=ScopedTickerArgs)
    async def start_research(ticker: str, runtime: ToolRuntime[Ctx]) -> dict[str, str]:
        """Put the desk on one company: the Analyst writes a stock story, the Checker re-checks
        every figure, and the Strategist sizes it against the investor's book and rules. It takes
        a few minutes and runs in the background, so this returns as soon as the team starts. Tell
        the investor it is running; you get the result in <research> on a later message, and read
        it with get_thesis. Starting a ticker the desk is already on returns that run. Use it when
        they ask what to do about a stock and there is no recent thesis, or they want a fresh read.
        """
        return await runs.start(user_of(runtime.context), ticker.upper())

    return start_research


def build_check_research(runs: "Runs") -> BaseTool:
    @tool(args_schema=Scoped)
    async def check_research(runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """How the research the desk is running is doing, for every ticker started and not yet
        reported. Use it when they ask whether the team is done. A finished run's thesis is read
        with get_thesis.
        """
        return {"runs": await runs.active(user_of(runtime.context))}

    return check_research


def build_get_thesis(pool: AsyncConnectionPool) -> BaseTool:
    @tool(args_schema=ScopedTickerArgs)
    async def get_thesis(ticker: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """The latest saved research on a ticker: story, review and advice, with its date.
        Check the date; prices and news move on.
        """
        saved = await theses.latest(pool, user_of(runtime.context), ticker)
        return {"found": False} if saved is None else {"found": True, **saved}

    return get_thesis
