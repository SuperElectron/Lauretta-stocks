"""Tools the chat assistant uses to put the desk to work and read what it saved.

Research takes minutes. `start_research` starts the run and waits with the investor while the
team works, relaying its progress; if it is still going after `RESEARCH_FOLLOW_S` the turn ends
and the run carries on, to be reported in the `<research>` block of a later turn
(`graph/research.py`). The run never belongs to the turn: nothing is lost by letting go of it.
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from src.db.queries import theses
from src.graph import emit
from src.graph.ctx import Ctx, user_of
from src.queue import keys
from src.tools.scoped import Scoped, ScopedTickerArgs
from src.worker.research import RESULT_FIELDS

if TYPE_CHECKING:
    from src.runs import Runs

# Runs the research team on a ticker for the run's user, passed on as the pipeline's context.
RunResearch = Callable[[str, Ctx], Awaitable[dict[str, Any]]]


def build_start_research(runs: "Runs", follow_s: float) -> BaseTool:
    @tool(args_schema=ScopedTickerArgs)
    async def start_research(ticker: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """Put the desk on one company: the Analyst writes a stock story, the Checker re-checks
        every figure, and the Strategist sizes it against the investor's book and rules. It takes
        a few minutes, which the investor watches; the result comes back here with each agent's
        current name in `names`. A team still working when the wait is up answers `"status":
        "running"` instead: say so, and you get the result in <research> on a later message.
        Starting a ticker the desk is already on joins that run. Use it when they ask what to do
        about a stock and there is no recent thesis, or they want a fresh read.
        """
        user = user_of(runtime.context)
        ticker = ticker.upper()
        await runs.start(user, ticker)
        result = await runs.follow(user, ticker, follow_s, _relay)
        if result is None:
            return {"ticker": ticker, "status": keys.RUNNING}
        if "error" in result:
            return {"ticker": ticker, "status": keys.FAILED, **result}
        return {field: result[field] for field in RESULT_FIELDS if field in result}

    return start_research


def _relay(stage: str, detail: str, name: str | None) -> None:
    """The run's progress, sent on as this turn's own, so the investor watches the team work."""
    emit.progress(stage, detail, name or "")


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
