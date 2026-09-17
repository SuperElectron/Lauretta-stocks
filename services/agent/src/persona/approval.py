"""Soul proposals: the investor decides by an exact phrase, and code applies it, never the model.

The chat graph checks each new investor message with `parse_decision`, applies it with `decide`
before the model runs, and tells the model what happened in a `<soul_change>` block. The reply
then ends with code-written text for the investor: `decision_notice` saying what the decision did,
and `proposal_notice` for each change proposed in the turn.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from psycopg_pool import AsyncConnectionPool

from src.db.queries import soul as queries
from src.prompts.assistant import SOUL_CHANGE

# Under a reply that proposed a soul change.
SOUL_PROPOSAL = """---
Proposed change to my soul (id {short_id})
Reason: {reason}

Proposed text:

{content}

Reply `approve soul {short_id}` to apply it, or `reject soul {short_id}` to discard it."""

# Under the reply to a message that approved or rejected a proposal, keyed by outcome;
# any other outcome uses "other". Fields: verb, short_id, outcome,
# reason, days.
SOUL_DECISION = {
    "approved": "---\nSoul change {short_id} applied: {reason}.",
    "rejected": "---\nSoul change {short_id} rejected: {reason}. The soul is unchanged.",
    "unknown": "---\nNo soul proposal {short_id} was found; nothing changed.",
    "ambiguous": "---\n{short_id} matches more than one soul proposal; nothing changed. Reply "
    "with more of the id.",
    "expired": "---\nSoul proposal {short_id} is older than {days} days and expired; nothing "
    "changed.",
    "stale": "---\nSoul proposal {short_id} was written against an older soul, so it was not "
    "applied; nothing changed. Ask for it to be proposed again.",
    "other": "---\nCould not {verb} soul proposal {short_id} ({outcome}); nothing changed.",
}

# The id shown to the investor: long enough not to collide within one investor's proposals.
SHORT_ID_CHARS = 8
# An old proposal was written against a soul and a conversation that may have moved on.
PROPOSAL_MAX_AGE = timedelta(days=7)
# Proposals waiting for a decision; another is refused until the investor decides one.
MAX_PENDING_PROPOSALS = 3
PROPOSE_TOOL = "propose_soul_change"

Verb = Literal["approve", "reject"]

# The short id shown, or more of the id up to the whole uuid, dashes included.
_DECISION = re.compile(r"(approve|reject) soul ([0-9a-f][0-9a-f-]{3,35})")


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


def _formatted(templates: dict[str, str], decision: dict[str, Any]) -> str:
    template = templates.get(decision["outcome"], templates["other"])
    return template.format(**decision, days=PROPOSAL_MAX_AGE.days)


def soul_change_block(verb: Verb, short_id: str, outcome: str, reason: str | None = None) -> str:
    decision = {"verb": verb, "short_id": short_id, "outcome": outcome, "reason": reason}
    return f"<soul_change>{_formatted(SOUL_CHANGE, decision)}</soul_change>"


def decision_notice(decision: dict[str, Any]) -> str:
    """What the investor sees under the reply to their decision, whatever the model says. Pure,
    beside `proposal_notice`."""
    return _formatted(SOUL_DECISION, decision)


async def decide(
    pool: AsyncConnectionPool, user_id: str, verb: Verb, short_id: str
) -> dict[str, Any]:
    """Applies or rejects the proposal. Returns what happened: verb, short_id, outcome (approved,
    rejected, stale, unknown, ambiguous, expired or already <status>) and the proposal's reason."""
    found = await queries.matching(pool, user_id, short_id)
    verdict = judge(found, datetime.now(UTC))
    decision = {"verb": verb, "short_id": short_id, "outcome": verdict, "reason": None}
    if verdict != "ok":
        return decision
    proposal = found[0]
    decision["reason"] = proposal["reason"]
    if verb == "approve":
        applied = await queries.approve(pool, user_id, proposal["id"])
        return {**decision, "outcome": "approved" if applied else "stale"}
    await queries.reject(pool, user_id, proposal["id"])
    return {**decision, "outcome": "rejected"}


def proposals_in_turn(messages: list[AnyMessage]) -> list[dict[str, Any]]:
    """The soul proposals stored since the investor's latest message, oldest first."""
    proposals = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if (
            isinstance(message, ToolMessage)
            and message.name == PROPOSE_TOOL
            and message.status != "error"
        ):
            result = json.loads(message.text)
            if result.get("proposed"):
                proposals.append(result)
    return proposals[::-1]


def proposal_notice(proposal: dict[str, Any]) -> str:
    """What the investor sees under the reply. Pure, so a streaming API can send it as an event."""
    return SOUL_PROPOSAL.format(
        short_id=proposal["proposal_id"], reason=proposal["reason"], content=proposal["content"]
    )
