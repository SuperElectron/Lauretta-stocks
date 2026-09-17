import pytest
from langchain_core.messages import AIMessage

from src.errors import RoleDidNotSubmit
from src.graph.role import build_role
from src.tools.submit import build_submit_review, build_submit_stock_story
from tests.utils import REVIEW, STORY, call, scripted


async def test_role_returns_what_it_submitted():
    model = scripted(call("submit_stock_story", STORY))
    analyst = build_role("analyst", model, [build_submit_stock_story()], recursion_limit=10)

    assert await analyst("prompt", "task") == STORY


async def test_role_that_stops_without_submitting_fails_hard():
    model = scripted(AIMessage(content="I think it is a buy."))
    analyst = build_role("analyst", model, [build_submit_stock_story()], recursion_limit=10)

    with pytest.raises(RoleDidNotSubmit):
        await analyst("prompt", "task")


async def test_invalid_submission_goes_back_to_the_model_to_fix():
    invalid = {**REVIEW, "verdict": "maybe"}
    model = scripted(
        call("submit_review", invalid, "call-1"), call("submit_review", REVIEW, "call-2")
    )
    checker = build_role("checker", model, [build_submit_review()], recursion_limit=10)

    assert await checker("prompt", "task") == REVIEW


async def test_roles_ask_the_model_for_one_tool_call_at_a_time():
    seen = {}

    class Recording(type(scripted())):
        def bind_tools(self, _tools, **kwargs):
            seen.update(kwargs)
            return self

    build_role("analyst", Recording(messages=iter([])), [build_submit_stock_story()], 10)
    assert seen == {"parallel_tool_calls": False}


async def test_reply_cut_off_by_the_token_limit_fails_with_its_own_error():
    from src.errors import ReplyTruncated

    cut = AIMessage(content="", response_metadata={"finish_reason": "length"})
    analyst = build_role("analyst", scripted(cut), [build_submit_stock_story()], 10)

    with pytest.raises(ReplyTruncated):
        await analyst("prompt", "task")
