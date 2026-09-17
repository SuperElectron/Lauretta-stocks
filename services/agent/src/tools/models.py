"""The arguments each tool accepts from the model. Anything else is a validation error."""

from typing import Annotated

from langchain_core.tools import InjectedToolCallId
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.graph.outputs import Advice, Review, StockStory
from src.memory.keys import SkippableStep
from src.memory.topics import Topic
from src.prompts import tools as wording
from src.prompts.soul import SOUL_MAX_CHARS


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


class FieldUpdateArgs(ToolArgs):
    @model_validator(mode="after")
    def _sets_something(self) -> "FieldUpdateArgs":
        if all(value is None for value in self.model_dump().values()):
            raise ValueError(wording.NOTHING_TO_SET)
        return self


class SetIdentityArgs(FieldUpdateArgs):
    name: str | None = Field(
        default=None, min_length=1, description="The name the investor chose for you."
    )
    analyst_name: str | None = Field(
        default=None, min_length=1, description="The name the investor chose for the Analyst."
    )
    checker_name: str | None = Field(
        default=None, min_length=1, description="The name the investor chose for the Checker."
    )
    strategist_name: str | None = Field(
        default=None, min_length=1, description="The name the investor chose for the Strategist."
    )
    emoji: str | None = Field(default=None, min_length=1, max_length=8)
    vibe: str | None = Field(
        default=None, min_length=1, max_length=200, description="Your manner in a few words."
    )


class SetUserDetailsArgs(FieldUpdateArgs):
    name: str | None = Field(default=None, min_length=1, description="Their name.")
    preferred_name: str | None = Field(
        default=None, min_length=1, description='What they want to be called, e.g. "Boss".'
    )
    city: str | None = Field(default=None, min_length=1, description="The city they live in.")
    country: str | None = Field(default=None, min_length=1, description="The country they live in.")
    currency: str | None = Field(
        default=None, min_length=3, max_length=3, description='ISO code, e.g. "GBP".'
    )
    timezone: str | None = Field(
        default=None, min_length=1, description='IANA name, e.g. "Europe/London".'
    )


class SkipSetupStepArgs(ToolArgs):
    step: SkippableStep = Field(
        description="team_names when they keep the desk's names; holdings when they hold "
        "nothing or would rather not say."
    )


class ProposeSoulArgs(ToolArgs):
    content: str = Field(
        min_length=1,
        max_length=SOUL_MAX_CHARS,
        description="The full new soul text (persona, voice, boundaries), not a diff.",
    )
    reason: str = Field(min_length=1, description="Why, in one sentence, in the investor's terms.")


class SubmitStoryArgs(StockStory):
    tool_call_id: Annotated[str, InjectedToolCallId]


class SubmitReviewArgs(Review):
    tool_call_id: Annotated[str, InjectedToolCallId]


class SubmitAdviceArgs(Advice):
    tool_call_id: Annotated[str, InjectedToolCallId]
