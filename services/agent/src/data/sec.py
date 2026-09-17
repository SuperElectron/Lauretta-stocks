"""SEC EDGAR: free, official fundamentals and filings for US-listed companies. No key.

EDGAR asks each client to send a User-Agent naming a contact, and to stay under 10 requests
a second. The ticker map is fetched once per process.
"""

from typing import Any

import httpx

from src.data.xbrl import annual_series, mark_stale
from src.errors import UpstreamUnavailable
from src.prompts import errors as wording

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DATA_URL = "https://data.sec.gov"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data"
FILING_FORMS = frozenset({"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K", "DEF 14A"})

# Each line item, and the "taxonomy:tag" a company may report it under. US filers use us-gaap;
# foreign filers (20-F, 40-F) use ifrs-full.
LINE_ITEMS: dict[str, tuple[str, ...]] = {
    "revenue": (
        # Revenues first: on a tie it is the total, the ASC 606 figure can be a subset.
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "ifrs-full:Revenue",
    ),
    "gross_profit": ("us-gaap:GrossProfit", "ifrs-full:GrossProfit"),
    "operating_income": (
        "us-gaap:OperatingIncomeLoss",
        "ifrs-full:ProfitLossFromOperatingActivities",
    ),
    "net_income": ("us-gaap:NetIncomeLoss", "ifrs-full:ProfitLossAttributableToOwnersOfParent"),
    "operating_cash_flow": (
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    ),
    "capex": (
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    ),
    "cash": (
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "ifrs-full:CashAndCashEquivalents",
    ),
    "long_term_debt": (
        "us-gaap:LongTermDebtNoncurrent",
        "us-gaap:LongTermDebt",
        "ifrs-full:LongtermBorrowings",
    ),
    "diluted_shares": (
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        "ifrs-full:AdjustedWeightedAverageShares",
    ),
}


class SecClient:
    """Raises `UpstreamUnavailable` on any failure to read EDGAR."""

    def __init__(self, user_agent: str, timeout: float = 30.0) -> None:
        self._headers = {"User-Agent": user_agent}
        self._timeout = timeout
        self._ciks: dict[str, int] | None = None

    async def cik(self, ticker: str) -> int | None:
        """The company's CIK, or None when EDGAR has no such ticker."""
        if self._ciks is None:
            listing = await self._get(TICKERS_URL)
            self._ciks = {row["ticker"].upper(): row["cik_str"] for row in listing.values()}
        return self._ciks.get(ticker.upper().replace(".", "-"))

    async def annual_financials(self, cik: int, years: int) -> dict[str, Any]:
        """The last `years` fiscal years of each line item, from annual filings."""
        facts = await self._get(f"{DATA_URL}/api/xbrl/companyfacts/CIK{cik:010d}.json")
        taxonomies = facts.get("facts", {})
        items = {name: annual_series(taxonomies, tags, years) for name, tags in LINE_ITEMS.items()}
        return {"company": facts.get("entityName"), "items": mark_stale(items)}

    async def recent_filings(self, cik: int, limit: int) -> list[dict[str, Any]]:
        """The latest periodic and event filings, newest first, with a link to each document."""
        submissions = await self._get(f"{DATA_URL}/submissions/CIK{cik:010d}.json")
        recent = submissions["filings"]["recent"]
        filings = []
        for index, form in enumerate(recent["form"]):
            if form not in FILING_FORMS:
                continue
            accession = recent["accessionNumber"][index]
            document = recent["primaryDocument"][index]
            filings.append(
                {
                    "form": form,
                    "filed": recent["filingDate"][index],
                    "period": recent["reportDate"][index] or None,
                    "items": recent["items"][index] or None,
                    "url": f"{ARCHIVE_URL}/{cik}/{accession.replace('-', '')}/{document}",
                }
            )
            if len(filings) == limit:
                break
        return filings

    async def _get(self, url: str) -> Any:
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                raise UpstreamUnavailable(
                    wording.SEC_UNREACHABLE.format(error=type(exc).__name__)
                ) from exc
        if response.status_code != 200:
            raise UpstreamUnavailable(wording.SEC_STATUS.format(status=response.status_code))
        return response.json()
