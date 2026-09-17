"""The arguments each tool accepts from the model. Anything else is a validation error."""

from typing import Annotated

from langchain_core.tools import InjectedToolCallId
from pydantic import BaseModel, ConfigDict, Field

from src.graph.outputs import Advice, Review, StockStory
from src.memory.topics import Topic


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TickerArgs(ToolArgs):
    ticker: str = Field(description='The exchange ticker, for example "MSFT" or "BRK-B".')


class NewsArgs(TickerArgs):
    limit: int = Field(default=8, ge=1, le=20, description="How many headlines.")


class FinancialsArgs(TickerArgs):
    years: int = Field(default=4, ge=1, le=10, description="How many fiscal years.")


class FilingsArgs(TickerArgs):
    limit: int = Field(default=8, ge=1, le=20, description="How many filings.")


class RememberArgs(ToolArgs):
    topic: Topic = Field(description="What the fact is about.")
    content: str = Field(
        description=(
            "One fact in the investor's terms, standalone and dated if it may change, for "
            'example "Max 10% of the portfolio in any single stock".'
        )
    )


class RecallArgs(ToolArgs):
    query: str = Field(description="What you want to know about the investor, in plain words.")
    limit: int = Field(default=5, ge=1, le=20)


class SetHoldingArgs(TickerArgs):
    shares: float = Field(gt=0, description="How many shares they hold now, in total.")
    avg_cost: float | None = Field(default=None, gt=0, description="Average cost per share.")
    note: str | None = Field(default=None, description="Anything they said about the position.")


class ForgetArgs(ToolArgs):
    memory_id: str = Field(description="The id of a memory from recall that is wrong or outdated.")


class SubmitStoryArgs(StockStory):
    tool_call_id: Annotated[str, InjectedToolCallId]


class SubmitReviewArgs(Review):
    tool_call_id: Annotated[str, InjectedToolCallId]


class SubmitAdviceArgs(Advice):
    tool_call_id: Annotated[str, InjectedToolCallId]
