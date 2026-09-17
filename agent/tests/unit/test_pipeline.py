from typing import Any

import pytest

from src.graph import pipeline as pipeline_module
from src.graph.pipeline import Team, build_pipeline, needs_revision
from tests.utils import ADVICE, REVIEW, STORY

REVISE = {**REVIEW, "verdict": "revise", "required_changes": ["Fix FY2026 revenue"]}


@pytest.mark.parametrize(
    ("verdict", "revisions", "expected"),
    [("revise", 0, True), ("revise", 1, False), ("approve", 0, False)],
)
def test_needs_revision(verdict, revisions, expected):
    state = {"review": {"verdict": verdict}, "revisions": revisions}
    assert needs_revision(state, max_revisions=1) is expected


class Recorder:
    """A role double that returns scripted results and keeps the prompts it was given."""

    def __init__(self, *results: dict[str, Any]) -> None:
        self.results = list(results)
        self.prompts: list[str] = []

    async def __call__(self, system_prompt: str, _task: str) -> dict[str, Any]:
        self.prompts.append(system_prompt)
        return self.results.pop(0)


@pytest.fixture
def no_database(monkeypatch):
    saved: dict[str, Any] = {}

    async def investor_blocks(_pool, _user_id):
        return "<investor>\nnothing yet\n</investor>", ["risk_tolerance"]

    async def advisor_user_block(_pool, _user_id):
        return "<user>\ncurrency: GBP\n</user>"

    async def save(_pool, _user_id, ticker, story, review, advice, revisions):
        saved.update(ticker=ticker, story=story, review=review, advice=advice, revisions=revisions)
        return "thesis-1"

    monkeypatch.setattr(pipeline_module, "investor_blocks", investor_blocks)
    monkeypatch.setattr(pipeline_module, "advisor_user_block", advisor_user_block)
    monkeypatch.setattr(pipeline_module.theses, "save", save)
    return saved


async def test_checker_sends_the_story_back_once_then_advisor_decides(no_database):
    analyst = Recorder(STORY, STORY)
    checker = Recorder(REVISE, REVISE)
    advisor = Recorder(ADVICE)
    graph = build_pipeline(None, "friend", Team(analyst, checker, advisor), max_revisions=1)

    final = await graph.ainvoke({"ticker": "MSFT"})

    assert final["revisions"] == 1
    assert final["thesis_id"] == "thesis-1"
    assert no_database["advice"] == ADVICE
    assert "Fix FY2026 revenue" in analyst.prompts[1]
    assert "last review" in checker.prompts[1]
    assert (
        "<previous_review>" in checker.prompts[1] and "<previous_review>" not in checker.prompts[0]
    )
    assert "Not yet known about the investor: risk_tolerance" in advisor.prompts[0]
    assert "currency: GBP" in advisor.prompts[0]
    assert "<user>" not in analyst.prompts[0] and "<user>" not in checker.prompts[0]


async def test_approved_story_goes_straight_to_the_advisor(no_database):
    team = Team(Recorder(STORY), Recorder(REVIEW), Recorder(ADVICE))
    final = await build_pipeline(None, "friend", team, max_revisions=1).ainvoke({"ticker": "MSFT"})

    assert final["revisions"] == 0
    assert no_database["review"]["verdict"] == "approve"
