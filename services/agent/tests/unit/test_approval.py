import json
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.db.queries import facts
from src.errors import PersonaInvalid
from src.graph import chat as chat_module
from src.graph.chat import build_chat
from src.graph.context import Known
from src.graph.ctx import Ctx
from src.persona import approval
from src.persona.approval import (
    decide,
    decision_notice,
    judge,
    parse_decision,
    proposal_notice,
    proposals_in_turn,
    soul_change_block,
)
from src.persona.layers import build_persona
from tests.utils import call, scripted

NOW = datetime(2026, 9, 16, tzinfo=UTC)
PROPOSAL = {"id": "3f2a1b9c-0000", "status": "proposed", "reason": "warmer", "created_at": NOW}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("approve soul 3f2a1b9c", ("approve", "3f2a1b9c")),
        ("  Reject   SOUL 3F2A1B9C \n", ("reject", "3f2a1b9c")),
        ("please approve soul 3f2a1b9c", None),
        ("approve soul 3f2a1b9c now", None),
        # More of the id, up to the whole uuid with its dashes, reaches "ask for the full id".
        (
            "approve soul 3f2a1b9c-0000-4f5a-8b7c-6d5e4f3a2b1c",
            ("approve", "3f2a1b9c-0000-4f5a-8b7c-6d5e4f3a2b1c"),
        ),
        ("approve soul -3f2a1b9c", None),
        ("approve soul xyz12345", None),
        ("approve soul", None),
    ],
)
def test_decision_phrase_is_the_whole_message(text, expected):
    assert parse_decision(text) == expected


def test_judge_outcomes():
    assert judge([], NOW) == "unknown"
    assert judge([PROPOSAL, PROPOSAL], NOW) == "ambiguous"
    assert judge([{**PROPOSAL, "status": "active"}], NOW) == "already active"
    assert judge([PROPOSAL], NOW + timedelta(days=8)) == "expired"
    assert judge([PROPOSAL], NOW + timedelta(days=1)) == "ok"


class Decided(list):
    """The decisions applied, in order. `current` False: the active soul moved on (stale)."""

    current = True


@pytest.fixture
def souls(monkeypatch):
    applied = Decided()
    found = [{**PROPOSAL, "created_at": datetime.now(UTC)}]

    async def matching(_pool, _user_id, short_id):
        return [row for row in found if row["id"].startswith(short_id)]

    async def approve(_pool, _user_id, proposal_id):
        applied.append(("approve", proposal_id))
        return applied.current

    async def reject(_pool, _user_id, proposal_id):
        applied.append(("reject", proposal_id))

    for name, double in [("matching", matching), ("approve", approve), ("reject", reject)]:
        monkeypatch.setattr(approval.queries, name, double)
    return applied


async def test_approve_applies_and_tells_the_model(souls):
    decision = await decide(None, "friend", "approve", "3f2a1b9c")
    assert souls == [("approve", "3f2a1b9c-0000")]
    assert decision == {"verb": "approve", "short_id": "3f2a1b9c", "outcome": "approved",
                        "reason": "warmer"}  # fmt: skip
    assert soul_change_block(**decision).startswith("<soul_change>approved 3f2a1b9c: warmer")


async def test_reject_and_unknown_ids(souls):
    assert (await decide(None, "friend", "reject", "3f2a1b9c"))["outcome"] == "rejected"
    unknown = await decide(None, "friend", "approve", "deadbeef")
    assert souls == [("reject", "3f2a1b9c-0000")]
    assert "no soul proposal deadbeef exists; nothing changed" in soul_change_block(**unknown)


async def test_a_stale_proposal_is_reported_and_changes_nothing(souls):
    souls.current = False
    decision = await decide(None, "friend", "approve", "3f2a1b9c")
    assert decision["outcome"] == "stale"
    assert "written against an older soul; nothing changed" in soul_change_block(**decision)
    assert "not applied; nothing changed" in decision_notice(decision)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("approved", "Soul change 3f2a1b9c applied: warmer."),
        ("rejected", "Soul change 3f2a1b9c rejected: warmer. The soul is unchanged."),
        ("unknown", "No soul proposal 3f2a1b9c was found; nothing changed."),
        ("ambiguous", "3f2a1b9c matches more than one soul proposal"),
        ("expired", "older than 7 days and expired"),
        ("stale", "written against an older soul"),
        ("already active", "Could not approve soul proposal 3f2a1b9c (already active)"),
    ],
)
def test_every_outcome_has_a_code_written_notice(outcome, expected):
    decision = {"verb": "approve", "short_id": "3f2a1b9c", "outcome": outcome, "reason": "warmer"}
    assert expected in decision_notice(decision)


def proposal_result(call_id: str = "call-1") -> ToolMessage:
    content = {"proposed": True, "proposal_id": "3f2a1b9c", "reason": "warmer",
               "content": "Be warm."}  # fmt: skip
    return ToolMessage(json.dumps(content), tool_call_id=call_id, name="propose_soul_change")


def test_notice_names_the_reason_text_and_exact_phrases():
    (proposal,) = proposals_in_turn([HumanMessage("be warmer"), proposal_result()])
    notice = proposal_notice(proposal)
    for part in ["id 3f2a1b9c", "Reason: warmer", "Be warm.", "`approve soul 3f2a1b9c`",
                 "`reject soul 3f2a1b9c`"]:  # fmt: skip
        assert part in notice


def test_only_this_turns_successful_proposals_count():
    failed = ToolMessage("boom", tool_call_id="c2", name="propose_soul_change", status="error")
    refused = ToolMessage('{"proposed": false, "note": "cap"}', tool_call_id="c3",
                          name="propose_soul_change")  # fmt: skip
    earlier = [proposal_result("c0"), HumanMessage("next")]
    assert proposals_in_turn([*earlier, failed, refused]) == []


async def test_signals_come_only_from_code_sources():
    with pytest.raises(PersonaInvalid):
        await facts.record_signals(None, None, "friend", {"channel": "cli"}, "chat")
    with pytest.raises(PersonaInvalid):
        await facts.set_many(None, None, "friend", "signal", {"bot_name": "Rex"}, "cli")


async def test_chat_applies_the_phrase_before_the_model_and_appends_notices(monkeypatch):
    decided = []

    async def load_known(_pool, _user_id):
        return Known(persona=build_persona([]), remembered=[], positions=[])

    async def theses_block(_pool, _user_id):
        return "<theses>\nnone yet\n</theses>"

    async def fake_decide(_pool, _user_id, verb, short_id):
        decided.append((verb, short_id))
        return {"verb": verb, "short_id": short_id, "outcome": "approved", "reason": "warmer"}

    for name, double in [("load_known", load_known), ("theses_block", theses_block),
                         ("decide", fake_decide)]:  # fmt: skip
        monkeypatch.setattr(chat_module, name, double)

    @tool
    async def propose_soul_change(content: str, reason: str) -> dict:
        """Propose."""
        return {"proposed": True, "proposal_id": "0badc0de", "reason": reason, "content": content}

    model = scripted(
        call("propose_soul_change", {"content": "Be warm.", "reason": "warmer"}),
        AIMessage("Proposed, boss."),
    )
    graph = build_chat(None, None, [propose_soul_change], model, 20)
    final = await graph.ainvoke(
        {"messages": [HumanMessage("approve soul 3f2a1b9c")]}, context=Ctx(user_id="friend")
    )

    assert decided == [("approve", "3f2a1b9c")]
    assert final["soul_change"].startswith("<soul_change>approved 3f2a1b9c")
    reply = final["messages"][-1]
    assert reply.text.startswith("Proposed, boss.")
    # What the decision did comes first, then the new proposal, both written by code.
    applied = reply.text.index("Soul change 3f2a1b9c applied: warmer.")
    assert applied < reply.text.index("`approve soul 0badc0de`")
    assert sum(isinstance(m, AIMessage) and not m.tool_calls for m in final["messages"]) == 1
