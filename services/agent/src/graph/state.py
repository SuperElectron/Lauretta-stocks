"""The state of each graph. Everything stored is plain JSON, so checkpoints need no allowlist."""

from typing import Any, Literal, TypedDict

from langgraph.graph import MessagesState

Stage = Literal["bootstrap", "onboard", "ready"]


class RoleState(MessagesState):
    """One research role's run: its prompt, its tool loop, and what it hands in."""

    system_prompt: str
    result: dict[str, Any] | None


class PipelineState(TypedDict, total=False):
    ticker: str
    investor: str
    # The investor's name, country and currency, for the advisor only.
    user: str
    unknown: list[str]
    story: dict[str, Any] | None
    review: dict[str, Any] | None
    advice: dict[str, Any] | None
    # Times the analyst has redrafted after the checker sent the story back.
    revisions: int
    thesis_id: str


class ChatState(MessagesState):
    # Rebuilt from the database before every model call, so tool writes show up at once.
    context: str
    # The soul, identity, user and signals blocks; rules are code and added at render.
    persona: str
    unknown: list[str]
    # What the assistant and the investor do not yet know to call each other.
    unnamed: list[str]
    # The `<soul_change>` block when this turn's message approved or rejected a proposal.
    soul_change: str


def stage(unknown: list[str], unnamed: list[str]) -> Stage:
    """Bootstrap until the investor's name is known, then onboard until the core investor
    profile is known. The model never decides this."""
    if unnamed:
        return "bootstrap"
    return "onboard" if unknown else "ready"
