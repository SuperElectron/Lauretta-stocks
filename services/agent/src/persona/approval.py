"""Soul proposals: the investor decides by an exact phrase, and code applies it, never the model.

The chat graph checks each new investor message with `parse_decision`, applies it with `decide`
before the model runs, and tells the model what happened in a `<soul_change>` block. After a
turn that proposed a change, `proposal_notice` is appended to the reply for the investor.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from psycopg_pool import AsyncConnectionPool

from src.db.queries import soul as queries
from src.prompts.assistant import SOUL_CHANGE
from src.prompts.notes import SOUL_PROPOSAL

# The id shown to the investor: long enough not to collide within one investor's proposals.
SHORT_ID_CHARS = 8
# An old proposal was written against a soul and a conversation that may have moved on.
PROPOSAL_MAX_AGE = timedelta(days=7)
PROPOSE_TOOL = "propose_soul_change"

Verb = Literal["approve", "reject"]

_DECISION = re.compile(r"(approve|reject) soul ([0-9a-f]{4,36})")


def parse_decision(text: str) -> tuple[Verb, str] | None:
    """`("approve", id)` or `("reject", id)` when the whole message is the phrase, else None."""
    match = _DECISION.fullmatch(" ".join(text.lower().split()))
    return None if match is None else (match.group(1), match.group(2))  # type: ignore[return-value]


def judge(found: list[dict[str, Any]], now: datetime) -> str:
    """ "ok" when exactly one live proposal matched, otherwise why it cannot be decided."""
    if not found:
        return "unknown"
    if len(found) > 1:
        return "ambiguous"
    (proposal,) = found
    if proposal["status"] != "proposed":
        return f"already {proposal['status']}"
    if now - proposal["created_at"] > PROPOSAL_MAX_AGE:
        return "expired"
    return "ok"


def soul_change_block(verb: Verb, short_id: str, outcome: str, reason: str | None = None) -> str:
    template = SOUL_CHANGE.get(outcome, SOUL_CHANGE["other"])
    text = template.format(
        verb=verb, short_id=short_id, outcome=outcome, reason=reason, days=PROPOSAL_MAX_AGE.days
    )
    return f"<soul_change>{text}</soul_change>"


async def decide(pool: AsyncConnectionPool, user_id: str, verb: Verb, short_id: str) -> str:
    """Applies or rejects the proposal; returns the `<soul_change>` block saying what happened."""
    found = await queries.matching(pool, user_id, short_id)
    verdict = judge(found, datetime.now(UTC))
    if verdict != "ok":
        return soul_change_block(verb, short_id, verdict)
    proposal = found[0]
    if verb == "approve":
        await queries.approve(pool, user_id, proposal["id"])
        return soul_change_block(verb, short_id, "approved", proposal["reason"])
    await queries.reject(pool, user_id, proposal["id"])
    return soul_change_block(verb, short_id, "rejected", proposal["reason"])


def proposals_in_turn(messages: list[AnyMessage]) -> list[dict[str, Any]]:
    """The soul proposals that succeeded since the investor's latest message, oldest first."""
    proposals = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if (
            isinstance(message, ToolMessage)
            and message.name == PROPOSE_TOOL
            and message.status != "error"
        ):
            proposals.append(json.loads(message.text))
    return proposals[::-1]


def proposal_notice(proposal: dict[str, Any]) -> str:
    """What the investor sees under the reply. Pure, so a streaming API can send it as an event."""
    return SOUL_PROPOSAL.format(
        short_id=proposal["proposal_id"], reason=proposal["reason"], content=proposal["content"]
    )
