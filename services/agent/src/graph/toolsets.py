"""Which tools each agent gets, in the order they are described to the model."""

from langchain_core.tools import BaseTool
from psycopg_pool import AsyncConnectionPool

from src.data.sec import SecClient
from src.memory.embedder import Embedder
from src.tools.filings import build_get_financials, build_get_recent_filings
from src.tools.market import build_get_market_snapshot, build_get_news, build_get_upcoming_events
from src.tools.memory import build_forget, build_recall, build_remember
from src.tools.persona import (
    build_propose_soul_change,
    build_set_identity,
    build_set_user_details,
    build_skip_setup_step,
)
from src.tools.portfolio import build_get_portfolio, build_remove_holding, build_set_holding
from src.tools.research import RunResearch, build_get_thesis, build_research_stock
from src.tools.submit import build_submit_advice, build_submit_review, build_submit_stock_story


def research_tools(sec: SecClient) -> list[BaseTool]:
    """What the analyst and the checker read. The checker gets the same, to re-verify."""
    return [
        build_get_market_snapshot(),
        build_get_financials(sec),
        build_get_recent_filings(sec),
        build_get_upcoming_events(),
        build_get_news(),
    ]


def analyst_tools(sec: SecClient) -> list[BaseTool]:
    return [*research_tools(sec), build_submit_stock_story()]


def checker_tools(sec: SecClient) -> list[BaseTool]:
    return [*research_tools(sec), build_submit_review()]


def advisor_tools(pool: AsyncConnectionPool, embedder: Embedder, user_id: str) -> list[BaseTool]:
    return [
        build_get_portfolio(pool, user_id),
        build_get_market_snapshot(),
        build_recall(pool, embedder, user_id),
        build_submit_advice(),
    ]


def assistant_tools(
    pool: AsyncConnectionPool, embedder: Embedder, user_id: str, run_research: RunResearch
) -> list[BaseTool]:
    return [
        build_remember(pool, embedder, user_id),
        build_recall(pool, embedder, user_id),
        build_forget(pool, user_id),
        build_set_holding(pool, user_id),
        build_remove_holding(pool, user_id),
        build_get_portfolio(pool, user_id),
        build_get_market_snapshot(),
        build_research_stock(run_research),
        build_get_thesis(pool, user_id),
        build_set_identity(pool, embedder, user_id),
        build_set_user_details(pool, embedder, user_id),
        build_skip_setup_step(pool, embedder, user_id),
        build_propose_soul_change(pool, embedder, user_id),
    ]
