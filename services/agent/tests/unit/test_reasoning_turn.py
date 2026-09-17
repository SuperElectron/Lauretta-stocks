"""Reasoning on a tool call goes back to the model for the rest of its turn, and no further."""

import inspect
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.graph import llm
from src.graph.ctx import Ctx
from src.graph.history import answered
from src.graph.reasoning import REASONING
from src.graph.role import build_role
from src.tools.submit import build_submit_stock_story
from src.worker.stream import run_chat
from tests.unit.openai_sse import model, reasoning_delta, tool_call
from tests.unit.test_worker_stream import Events
from tests.utils import STORY


@tool
async def lookup() -> str:
    """Looks something up."""
    return "42"


def chat(chat_model: Any) -> Any:
    """The chat graph's loop as `graph/chat.py` runs it: history, backoff, then `complete`."""
    bound = llm.with_backoff(chat_model.bind_tools([lookup]))

    async def agent(state: MessagesState) -> dict[str, object]:
        return {"messages": [llm.complete(await bound.ainvoke(answered(state["messages"])))]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode([lookup]))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=InMemorySaver())


def assistant_messages(request: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in request["messages"] if m["role"] == "assistant"]


def test_the_private_chatopenai_hooks_the_round_trip_relies_on_are_still_there():
    params = list(inspect.signature(BaseChatOpenAI._get_request_payload).parameters)
    assert params == ["self", "input_", "stop", "kwargs"], params
    params = list(inspect.signature(BaseChatOpenAI._create_chat_result).parameters)
    assert params == ["self", "response", "generation_info"], params


TOOL_TURN = ([reasoning_delta("Check the price first."), tool_call("lookup", {})], "tool_calls")


async def test_the_tool_calls_reasoning_is_sent_back_within_the_turn():
    requests: list[dict[str, Any]] = []
    answer = ([reasoning_delta("It is 42."), {"content": "42"}], "stop")
    graph = chat(model(TOOL_TURN, answer, requests=requests))
    config = {"configurable": {"thread_id": "t"}}

    await graph.ainvoke({"messages": [HumanMessage("price?")]}, config)

    assert len(requests) == 2
    [sent] = assistant_messages(requests[1])
    assert sent["tool_calls"][0]["function"]["name"] == "lookup"
    assert sent["reasoning"] == "Check the price first."
    assert "reasoning_content" not in sent
    final = (await graph.aget_state(config)).values["messages"][-1]
    assert final.text == "42" and REASONING not in final.additional_kwargs


async def test_streamed_as_the_worker_runs_chat_the_reasoning_is_sent_back_once():
    requests: list[dict[str, Any]] = []
    answer = ([reasoning_delta("It is 42."), {"content": "42"}], "stop")
    events = Events()

    result = await run_chat(chat(model(TOOL_TURN, answer, requests=requests)), "mat", "t",
                            "a" * 32, "price?", events)  # fmt: skip

    assert result["reply"] == "42" and requests[1]["stream"] is True
    assert [m.get("reasoning") for m in assistant_messages(requests[1])] == [
        "Check the price first."
    ]
    # Sent to the client once, though the tool call's copy stays in the turn's state.
    assert (
        "".join(d["text"] for k, d in events if k == "reasoning")
        == "Check the price first.It is 42."
    )


async def test_earlier_turns_are_sent_without_their_reasoning():
    requests: list[dict[str, Any]] = []
    answer = ([{"content": "42"}], "stop")
    graph = chat(model(TOOL_TURN, answer, answer, requests=requests))
    config = {"configurable": {"thread_id": "t"}}

    await graph.ainvoke({"messages": [HumanMessage("price?")]}, config)
    await graph.ainvoke({"messages": [HumanMessage("again?")]}, config)

    earlier = assistant_messages(requests[2])
    assert [bool(m.get("tool_calls")) for m in earlier] == [True, False]
    assert all("reasoning" not in m for m in earlier)


async def test_a_research_role_sends_its_reasoning_back_until_it_submits():
    requests: list[dict[str, Any]] = []
    analyst = model(
        ([reasoning_delta("Draft, then submit."), tool_call("lookup", {})], "tool_calls"),
        ([reasoning_delta("Submit."), tool_call("submit_stock_story", STORY, "c2")], "tool_calls"),
        requests=requests,
    )
    role = build_role("analyst", analyst, [lookup, build_submit_stock_story()], 10)

    assert await role("You are the analyst.", "Research MSFT.", Ctx(user_id="mat")) == STORY
    assert [m.get("reasoning") for m in assistant_messages(requests[1])] == ["Draft, then submit."]


def test_answered_strips_reasoning_before_the_latest_human_message_only():
    def thinking_call(call_id: str) -> AIMessage:
        return AIMessage("", tool_calls=[{"name": "lookup", "args": {}, "id": call_id}],
                         additional_kwargs={REASONING: call_id, "other": 1})  # fmt: skip

    messages = [HumanMessage("one"), thinking_call("c1"), ToolMessage("{}", tool_call_id="c1"),
                AIMessage("done"), HumanMessage("two"), thinking_call("c2"),
                ToolMessage("{}", tool_call_id="c2")]  # fmt: skip
    shown = [m for m in answered(messages) if isinstance(m, AIMessage) and m.tool_calls]
    assert [m.additional_kwargs for m in shown] == [{"other": 1}, {REASONING: "c2", "other": 1}]


def test_complete_keeps_reasoning_on_a_tool_call():
    reply = AIMessage("", tool_calls=[{"name": "lookup", "args": {}, "id": "c1"}],
                      additional_kwargs={REASONING: "plan"})  # fmt: skip
    assert llm.complete(reply).additional_kwargs == {REASONING: "plan"}
