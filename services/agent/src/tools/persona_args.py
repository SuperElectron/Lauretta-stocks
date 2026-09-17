"""The arguments of the persona tools: the desk's identity, the investor's details, setup skips
and soul proposals. Every value is rendered into a prompt block, so none may hold `<` or `>`."""

from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from src.memory.keys import SkippableStep
from src.prompts import tools as wording
from src.prompts.soul import SOUL_MAX_CHARS
from src.tools.models import ToolArgs

# Names go into every system prompt, progress line and report.
NAME_MAX_CHARS = 40
# Other profile values (city, country, timezone) render in the prompt's <user> block.
DETAIL_MAX_CHARS = 80


def _no_angle_brackets(value: str) -> str:
    if "<" in value or ">" in value:
        raise ValueError(wording.ANGLE_BRACKETS)
    return value


# A value rendered inside a prompt block: stripped, and never able to open or close a tag.
PromptText = Annotated[
    str, StringConstraints(strip_whitespace=True), AfterValidator(_no_angle_brackets)
]


class FieldUpdateArgs(ToolArgs):
    @model_validator(mode="after")
    def _sets_something(self) -> "FieldUpdateArgs":
        given = (getattr(self, name) for name in type(self).model_fields if name != "runtime")
        if all(value is None for value in given):
            raise ValueError(wording.NOTHING_TO_SET)
        return self


class SetIdentityArgs(FieldUpdateArgs):
    name: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=NAME_MAX_CHARS,
        description="The name the investor chose for you.",
    )
    analyst_name: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=NAME_MAX_CHARS,
        description="The name the investor chose for the Analyst.",
    )
    checker_name: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=NAME_MAX_CHARS,
        description="The name the investor chose for the Checker.",
    )
    strategist_name: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=NAME_MAX_CHARS,
        description="The name the investor chose for the Strategist.",
    )
    emoji: PromptText | None = Field(default=None, min_length=1, max_length=8)
    vibe: PromptText | None = Field(
        default=None, min_length=1, max_length=200, description="Your manner in a few words."
    )


class SetUserDetailsArgs(FieldUpdateArgs):
    name: PromptText | None = Field(
        default=None, min_length=1, max_length=NAME_MAX_CHARS, description="Their name."
    )
    preferred_name: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=NAME_MAX_CHARS,
        description='What they want to be called, e.g. "Boss".',
    )
    city: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=DETAIL_MAX_CHARS,
        description="The city they live in.",
    )
    country: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=DETAIL_MAX_CHARS,
        description="The country they live in.",
    )
    currency: PromptText | None = Field(
        default=None, min_length=3, max_length=3, description='ISO code, e.g. "GBP".'
    )
    timezone: PromptText | None = Field(
        default=None,
        min_length=1,
        max_length=DETAIL_MAX_CHARS,
        description='IANA name, e.g. "Europe/London".',
    )


class SkipSetupStepArgs(ToolArgs):
    step: SkippableStep = Field(
        description="team_names when they keep the desk's names; holdings when they hold "
        "nothing or would rather not say."
    )


class ProposeSoulArgs(ToolArgs):
    content: PromptText = Field(
        min_length=1,
        max_length=SOUL_MAX_CHARS,
        description="The full new soul text (persona, voice, boundaries), not a diff.",
    )
    reason: PromptText = Field(
        min_length=1, max_length=300, description="Why, in one sentence, in the investor's terms."
    )
