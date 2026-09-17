"""What each research role hands in. These are also the arguments of its submit tool."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataPoint(Output):
    metric: str = Field(description='What was measured, for example "revenue" or "forward P/E".')
    value: str = Field(description='The figure as the tool returned it, with units: "$331.8B".')
    period: str = Field(description='When it applies: "FY ending 2026-06-30", "as of 2026-09-16".')
    source: str = Field(description='The tool it came from: "get_financials (SEC 10-K)".')


class StockStory(Output):
    business: str = Field(description="What they sell, to whom, and where. Two or three sentences.")
    driver: str = Field(description="What could change revenue, margins, cash flow or multiple.")
    market_gap: str = Field(description="What the market may be under- or overestimating, as a "
                            "claim that can be checked.")  # fmt: skip
    catalyst: str = Field(description="The event that will test the thesis.")
    catalyst_date: str | None = Field(
        description="ISO date of the catalyst from a tool result, or null if none was found."
    )
    falsifier: str = Field(
        description="An observable outcome that proves the thesis wrong: metric, threshold, when."
    )
    risks: list[str] = Field(description="Three to five material risks, one sentence each.")
    data_snapshot: list[DataPoint] = Field(description="Every figure the story relies on.")
    data_gaps: list[str] = Field(description="What could not be retrieved and would matter.")
    confidence: Literal["low", "medium", "high"]


class Review(Output):
    verdict: Literal["approve", "revise"]
    summary: str = Field(description="The thesis in two sentences, as you understand it.")
    strengths: list[str]
    weaknesses: list[str]
    data_issues: list[str] = Field(
        description="Each figure that does not match your own lookup, with both values."
    )
    missing_information: list[str]
    required_changes: list[str] = Field(
        description="Concrete instructions for the analyst. Empty when the verdict is approve."
    )


class Advice(Output):
    action: Literal["buy", "add", "hold", "trim", "sell", "watch", "avoid"]
    target_weight_pct: float | None = Field(
        description="Suggested weight of the portfolio after acting, or null when not sizing."
    )
    rationale: str = Field(description="Why, in two to four sentences.")
    portfolio_fit: str = Field(description="Concentration, overlap and how it fits their rules.")
    key_risks: list[str]
    change_my_mind: list[str] = Field(
        description="Specific conditions that would change this suggestion."
    )
    questions_for_investor: list[str] = Field(
        description="What you need to know from them to advise better. Empty if nothing."
    )
