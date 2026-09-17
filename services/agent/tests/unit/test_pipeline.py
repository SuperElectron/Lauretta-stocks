import pytest

from src.graph.ctx import Ctx
from src.graph.pipeline import Team, build_pipeline, needs_revision
from tests.utils import ADVICE, REVIEW, STORY, Recorder

FRIEND = Ctx(user_id="friend")
REVISE = {**REVIEW, "verdict": "revise", "required_changes": ["Fix FY2026 revenue"]}


@pytest.mark.parametrize(
    ("verdict", "revisions", "expected"),
    [("revise", 0, True), ("revise", 1, False), ("approve", 0, False)],
)
def test_needs_revision(verdict, revisions, expected):
    state = {"review": {"verdict": verdict}, "revisions": revisions}
    assert needs_revision(state, max_revisions=1) is expected


async def test_checker_sends_the_story_back_once_then_advisor_decides(no_database):
    analyst = Recorder(STORY, STORY)
    checker = Recorder(REVISE, REVISE)
    advisor = Recorder(ADVICE)
    graph = build_pipeline(None, Team(analyst, checker, advisor), max_revisions=1)

    final = await graph.ainvoke({"ticker": "MSFT"}, context=FRIEND)

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
    graph = build_pipeline(None, team, max_revisions=1)
    final = await graph.ainvoke({"ticker": "MSFT"}, context=FRIEND)

    assert final["revisions"] == 0
    assert no_database["review"]["verdict"] == "approve"
