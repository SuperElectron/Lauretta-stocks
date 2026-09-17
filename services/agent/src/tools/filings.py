"""Tools that read SEC EDGAR: annual financials and recent filings of SEC registrants."""

from typing import Any

from langchain_core.tools import BaseTool, tool

from src.data.sec import SecClient
from src.errors import UpstreamUnavailable
from src.tools.market import unavailable
from src.tools.models import FilingsArgs, FinancialsArgs

NOT_REGISTERED_REASON = (
    "no SEC registrant has this ticker; EDGAR covers US-listed shares and ADRs only"
)

NOT_REGISTERED = {
    "found": False,
    "reason": NOT_REGISTERED_REASON,
}


def build_get_financials(sec: SecClient) -> BaseTool:
    @tool(args_schema=FinancialsArgs)
    async def get_financials(ticker: str, years: int = 4) -> dict[str, Any]:
        """Annual figures from the company's 10-K, or 20-F/40-F for foreign filers: revenue,
        gross profit, operating income, net income, operating cash flow, capex, cash,
        long-term debt and diluted shares. Values are in the unit given (USD, CAD, shares),
        newest fiscal year first. Free
        cash flow is operating cash flow minus capex. An item with `found: false` was not
        reported under the usual tags; say so rather than estimate it. An item with
        `stale: true` stopped being reported under that tag years ago; do not use it as current.
        """
        try:
            cik = await sec.cik(ticker)
            if cik is None:
                return NOT_REGISTERED
            return {"found": True, **await sec.annual_financials(cik, years)}
        except UpstreamUnavailable as exc:
            return unavailable(exc)

    return get_financials


def build_get_recent_filings(sec: SecClient) -> BaseTool:
    @tool(args_schema=FilingsArgs)
    async def get_recent_filings(ticker: str, limit: int = 8) -> dict[str, Any]:
        """The latest 10-K, 10-Q, 8-K and proxy filings (20-F, 40-F and 6-K for foreign
        filers) with their dates, 8-K item numbers and links. Use it to date the latest
        results and spot material events (8-K items such as 1.01 agreements, 2.02 results,
        5.02 executive changes).
        """
        try:
            cik = await sec.cik(ticker)
            if cik is None:
                return NOT_REGISTERED
            return {"found": True, "filings": await sec.recent_filings(cik, limit)}
        except UpstreamUnavailable as exc:
            return unavailable(exc)

    return get_recent_filings
