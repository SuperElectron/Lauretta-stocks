"""Tools that read Yahoo Finance: snapshot, news, and upcoming events."""

from typing import Any

from langchain_core.tools import BaseTool, tool

from src.data import market
from src.errors import UpstreamUnavailable
from src.tools.models import NewsArgs, TickerArgs


def unavailable(exc: UpstreamUnavailable) -> dict[str, Any]:
    return {"available": False, "reason": str(exc)}


def build_get_market_snapshot() -> BaseTool:
    @tool(args_schema=TickerArgs)
    async def get_market_snapshot(ticker: str) -> dict[str, Any]:
        """Price, market cap, valuation multiples, margins, growth, analyst target and
        trailing returns as Yahoo Finance reports them today. Margins and growth are
        fractions (0.45 is 45%); dividendYield and returns are already percentages.
        `found: false` means Yahoo has no such ticker; `available: false` means Yahoo could
        not be read.
        """
        try:
            return await market.snapshot(ticker)
        except UpstreamUnavailable as exc:
            return unavailable(exc)

    return get_market_snapshot


def build_get_news() -> BaseTool:
    @tool(args_schema=NewsArgs)
    async def get_news(ticker: str, limit: int = 8) -> dict[str, Any]:
        """Recent headlines about the company with a one-line summary, publisher, date and
        link. Headlines are claims by the publisher, not verified facts.
        """
        try:
            return {"stories": await market.news(ticker, limit)}
        except UpstreamUnavailable as exc:
            return unavailable(exc)

    return get_news


def build_get_upcoming_events() -> BaseTool:
    @tool(args_schema=TickerArgs)
    async def get_upcoming_events(ticker: str) -> dict[str, Any]:
        """The next earnings date with the consensus EPS and revenue range, and dividend
        dates. Use it for a dated catalyst. Empty when Yahoo has no calendar.
        """
        try:
            return {"events": await market.events(ticker)}
        except UpstreamUnavailable as exc:
            return unavailable(exc)

    return get_upcoming_events
