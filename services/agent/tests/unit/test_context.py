from src.data.market import trailing_returns
from src.db.queries.memories import content_hash
from src.graph.context import render_holdings, render_investor, unknown_topics
from src.graph.render import render_assistant_prompt
from src.graph.state import stage
from src.persona.layers import build_persona, desk_names
from src.tools.portfolio import valued

MEMORY = {"id": "m1", "topic": "risk_tolerance", "content": "Medium risk", "created": "2026-09-16"}


def test_investor_block_lists_facts_by_topic_with_dates_and_ids():
    block = render_investor([MEMORY])
    assert "risk_tolerance: Medium risk (2026-09-16, id m1)" in block


def test_unknown_core_topics_drive_the_stage():
    unknown = unknown_topics([MEMORY])
    assert "risk_tolerance" not in unknown and "goals" in unknown
    assert stage(unknown, []) == "onboard"
    assert stage([], []) == "ready"


def test_assistant_prompt_carries_stage_and_unknowns():
    investor = "<investor>\nnothing yet\n</investor>"
    names = desk_names(build_persona([]))
    prompt = render_assistant_prompt("<soul>s</soul>", investor, ["goals"], [], "onboard", names)
    assert "<unknown>goals</unknown>" in prompt
    assert "<stage>onboard:" in prompt


def test_holdings_block():
    positions = [{"ticker": "MSFT", "shares": 10.0, "avg_cost": 300.0, "note": None}]
    assert "MSFT: 10 shares @ 300" in render_holdings(positions)
    assert "none recorded" in render_holdings([])


def test_portfolio_weights_cover_priced_positions_only():
    positions = [
        {"ticker": "A", "shares": 10.0},
        {"ticker": "B", "shares": 30.0},
        {"ticker": "C", "shares": 1.0},
    ]
    result = valued(positions, {"A": 10.0, "B": 10.0, "C": None})
    weights = {row["ticker"]: row["weight_pct"] for row in result["positions"]}
    assert weights == {"A": 25.0, "B": 75.0, "C": None}
    assert result["unpriced"] == ["C"]


def test_memory_hash_ignores_case_and_spacing_but_not_topic():
    assert content_hash("goals", "Retire  at 55") == content_hash("goals", "retire at 55")
    assert content_hash("goals", "retire at 55") != content_hash("other", "retire at 55")


def test_trailing_returns_none_when_history_is_short():
    closes = [100.0] * 30 + [110.0]
    assert trailing_returns(closes) == {"1m": 10.0, "3m": None, "6m": None, "1y": None}
