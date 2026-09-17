"""The state of each graph. Everything stored is plain JSON, so checkpoints need no allowlist."""

from typing import Any, Literal, TypedDict

from langgraph.graph import MessagesState

Stage = Literal["setup", "ready"]
# How a turn opens the thread (`graph/setup.opening`): first-contact intro, greeting, or neither.
Opening = Literal["intro", "welcome", ""]


class RoleState(MessagesState):
    """One research role's run: its prompt, its tool loop, and what it hands in."""

    system_prompt: str
    result: dict[str, Any] | None
    # Times the role was reminded to submit after replying without a tool call.
    reminders: int


class PipelineState(TypedDict, total=False):
    ticker: str
    investor: str
    # The investor's name, country and currency, for the advisor only.
    user: str
    unknown: list[str]
    # Each desk agent's current name, by name key (`bot_name`, `analyst_name`, ...).
    names: dict[str, str]
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
    # The guided setup (`graph/setup.py`): each step's status.
    setup: list[dict[str, Any]]
    # Each desk agent's current name, by name key.
    names: dict[str, str]
    # The `<soul_change>` block when this turn's message approved or rejected a proposal.
    soul_change: str
    # What that decision did (`persona/approval.decide`), for the notice; empty otherwise.
    soul_decision: dict[str, Any]
    opening: Opening
    # What the desk is researching or has just finished (`graph/research.py`), for this turn.
    research: str
    # The running summary of the messages before `summarized` (`graph/compaction.py`).
    summary: str
    summarized: int
