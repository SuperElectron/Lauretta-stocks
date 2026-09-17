import json
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.db.queries import facts
from src.errors import PersonaInvalid
from src.graph import chat as chat_module
from src.graph.chat import build_chat
from src.persona import approval
from src.persona.approval import (
    decide,
    judge,
    parse_decision,
    proposal_notice,
    proposals_in_turn,
)
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


@pytest.fixture
def souls(monkeypatch):
    applied: list[tuple[str, str]] = []
    found = [{**PROPOSAL, "created_at": datetime.now(UTC)}]

    async def matching(_pool, _user_id, short_id):
        return [row for row in found if row["id"].startswith(short_id)]

    async def approve(_pool, _user_id, proposal_id):
        applied.append(("approve", proposal_id))

    async def reject(_pool, _user_id, proposal_id):
        applied.append(("reject", proposal_id))

    for name, double in [("matching", matching), ("approve", approve), ("reject", reject)]:
        monkeypatch.setattr(approval.queries, name, double)
    return applied


async def test_approve_applies_and_tells_the_model(souls):
    block = await decide(None, "friend", "approve", "3f2a1b9c")
    assert souls == [("approve", "3f2a1b9c-0000")]
    assert block.startswith("<soul_change>approved 3f2a1b9c: warmer")


async def test_reject_and_unknown_ids(souls):
    assert "rejected 3f2a1b9c" in await decide(None, "friend", "reject", "3f2a1b9c")
    unknown = await decide(None, "friend", "approve", "deadbeef")
    assert souls == [("reject", "3f2a1b9c-0000")]
    assert "no soul proposal deadbeef exists; nothing changed" in unknown


def proposal_result(call_id: str = "call-1") -> ToolMessage:
    content = {"proposal_id": "3f2a1b9c", "reason": "warmer", "content": "Be warm."}
    return ToolMessage(json.dumps(content), tool_call_id=call_id, name="propose_soul_change")


def test_notice_names_the_reason_text_and_exact_phrases():
    (proposal,) = proposals_in_turn([HumanMessage("be warmer"), proposal_result()])
    notice = proposal_notice(proposal)
    for part in ["id 3f2a1b9c", "Reason: warmer", "Be warm.", "`approve soul 3f2a1b9c`",
                 "`reject soul 3f2a1b9c`"]:  # fmt: skip
        assert part in notice


def test_only_this_turns_successful_proposals_count():
    failed = ToolMessage("boom", tool_call_id="c2", name="propose_soul_change", status="error")
    earlier = [proposal_result("c0"), HumanMessage("next")]
    assert proposals_in_turn([*earlier, failed]) == []


async def test_signals_come_only_from_code_sources():
    with pytest.raises(PersonaInvalid):
        await facts.record_signals(None, None, "friend", {"channel": "cli"}, "chat")
    with pytest.raises(PersonaInvalid):
        await facts.set_many(None, None, "friend", "signal", {"bot_name": "Rex"}, "cli")


async def test_chat_applies_the_phrase_before_the_model_and_appends_notices(monkeypatch):
    decided = []

    async def blocks(_pool, _user_id):
        return "<soul>s</soul>", []

    async def theses_block(_pool, _user_id):
        return "<theses>\nnone yet\n</theses>"

    async def fake_decide(_pool, _user_id, verb, short_id):
        decided.append((verb, short_id))
        return f"<soul_change>approved {short_id}: warmer.</soul_change>"

    for name, double in [("persona_blocks", blocks), ("investor_blocks", blocks),
                         ("theses_block", theses_block), ("decide", fake_decide)]:  # fmt: skip
        monkeypatch.setattr(chat_module, name, double)

    @tool
    async def propose_soul_change(content: str, reason: str) -> dict:
        """Propose."""
        return {"proposal_id": "0badc0de", "reason": reason, "content": content}

    model = scripted(
        call("propose_soul_change", {"content": "Be warm.", "reason": "warmer"}),
        AIMessage("Proposed, Your Excellency."),
    )
    graph = build_chat(None, "friend", None, [propose_soul_change], model, 20)
    final = await graph.ainvoke({"messages": [HumanMessage("approve soul 3f2a1b9c")]})

    assert decided == [("approve", "3f2a1b9c")]
    assert final["soul_change"].startswith("<soul_change>approved 3f2a1b9c")
    reply = final["messages"][-1]
    assert reply.text.startswith("Proposed, Your Excellency.")
    assert "`approve soul 0badc0de`" in reply.text
    assert sum(isinstance(m, AIMessage) and not m.tool_calls for m in final["messages"]) == 1
