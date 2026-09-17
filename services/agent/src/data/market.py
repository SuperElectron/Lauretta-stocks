"""Yahoo Finance through yfinance: quotes, valuation, news and event dates. Free, no key.

yfinance is unofficial and blocking, so every call runs in a thread and any failure is
reported as `UpstreamUnavailable`.
"""

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import yfinance as yf

from src.errors import UpstreamUnavailable
from src.prompts import errors as wording

SNAPSHOT_FIELDS = (
    "longName", "quoteType", "sector", "industry", "country", "currency", "exchange",
    "currentPrice", "marketCap", "enterpriseValue", "trailingPE", "forwardPE", "priceToBook",
    "enterpriseToEbitda", "dividendYield", "beta", "fiftyTwoWeekLow", "fiftyTwoWeekHigh",
    "revenueGrowth", "grossMargins", "operatingMargins", "profitMargins", "freeCashflow",
    "totalCash", "totalDebt", "targetMeanPrice", "recommendationKey", "numberOfAnalystOpinions",
)  # fmt: skip
SUMMARY_CHARS = 700
RETURN_WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "1y": 250}


async def snapshot(ticker: str) -> dict[str, Any]:
    """Price, valuation and margins as Yahoo reports them now, plus trailing returns."""
    info = await _call(lambda: yf.Ticker(ticker).info)
    if not info or info.get("currentPrice") is None and info.get("regularMarketPrice") is None:
        return {"found": False}
    result = {field: info.get(field) for field in SNAPSHOT_FIELDS}
    result["currentPrice"] = info.get("currentPrice") or info.get("regularMarketPrice")
    result["business_summary"] = (info.get("longBusinessSummary") or "")[:SUMMARY_CHARS]
    history = await _call(lambda: yf.Ticker(ticker).history(period="1y").get("Close"))
    result["returns"] = trailing_returns([] if history is None else history.tolist())
    return {"found": True, "as_of": date.today().isoformat(), **result}


async def prices(tickers: list[str]) -> dict[str, float | None]:
    """The latest price for each ticker, or None where Yahoo has none."""

    async def one(ticker: str) -> float | None:
        # A delisted or mistyped ticker has no price; it must not hide the others.
        try:
            return await _call(lambda: yf.Ticker(ticker).fast_info.get("lastPrice"))
        except UpstreamUnavailable:
            return None

    found = await asyncio.gather(*(one(ticker) for ticker in tickers))
    return dict(zip(tickers, found, strict=True))


async def news(ticker: str, limit: int) -> list[dict[str, Any]]:
    """Recent headlines, newest first as Yahoo orders them."""
    items = await _call(lambda: yf.Ticker(ticker).news) or []
    stories = []
    for item in items[:limit]:
        content = item.get("content") or {}
        stories.append(
            {
                "title": content.get("title"),
                "summary": content.get("summary"),
                "published": content.get("pubDate"),
                "publisher": (content.get("provider") or {}).get("displayName"),
                "url": (content.get("canonicalUrl") or {}).get("url"),
            }
        )
    return stories


async def events(ticker: str) -> dict[str, Any]:
    """Upcoming earnings and dividend dates, with the consensus range for the next report."""
    calendar = await _call(lambda: yf.Ticker(ticker).calendar) or {}
    return {name: _plain(value) for name, value in calendar.items()}


def trailing_returns(closes: list[float]) -> dict[str, float | None]:
    """Percentage change over each window, None where the history is too short."""
    returns: dict[str, float | None] = {}
    for name, days in RETURN_WINDOWS.items():
        if len(closes) > days and closes[-days - 1]:
            returns[name] = round((closes[-1] / closes[-days - 1] - 1) * 100, 1)
        else:
            returns[name] = None
    return returns


def _plain(value: Any) -> Any:
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


async def _call[T](load: Callable[[], T]) -> T:
    try:
        return await asyncio.to_thread(load)
    except Exception as exc:
        raise UpstreamUnavailable(wording.YAHOO_FAILED.format(error=type(exc).__name__)) from exc
