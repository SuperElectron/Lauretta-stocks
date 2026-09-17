from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.graph.history import UNFINISHED, answered, recent


def tool_call(call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "recall", "args": {}, "id": call_id}])


def test_failed_turn_gets_a_result_for_each_unanswered_call():
    messages = [HumanMessage("hi"), tool_call("c1"), HumanMessage("again")]
    shown = answered(messages)
    assert isinstance(shown[2], ToolMessage)
    assert shown[2].tool_call_id == "c1" and shown[2].content == UNFINISHED
    assert shown[3].content == "again"


def test_answered_calls_and_empty_replies():
    messages = [HumanMessage("hi"), tool_call("c1"), ToolMessage("{}", tool_call_id="c1"),
                AIMessage(content=""), HumanMessage("next")]  # fmt: skip
    shown = answered(messages)
    assert [type(m).__name__ for m in shown] == ["HumanMessage", "AIMessage", "ToolMessage",
                                                  "HumanMessage"]  # fmt: skip


def test_window_starts_at_a_human_turn():
    messages = [HumanMessage("hi"), tool_call("c1"), ToolMessage("{}", tool_call_id="c1"),
                AIMessage("ok"), HumanMessage("next"), AIMessage("sure")]  # fmt: skip
    assert recent(messages, 4)[0].content == "next"


def test_window_inside_one_long_turn_never_opens_on_a_tool_result():
    messages = [tool_call("c1"), ToolMessage("{}", tool_call_id="c1"), tool_call("c2"),
                ToolMessage("{}", tool_call_id="c2")]  # fmt: skip
    assert isinstance(recent(messages, 3)[0], AIMessage)
