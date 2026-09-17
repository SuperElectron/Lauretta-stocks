"""Which reasoning the chat relay sends, how it is guarded, and a real nested research role."""

from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.graph import llm
from src.graph.reasoning import REASONING
from src.graph.role import build_role
from src.prompts import progress
from src.tools.submit import build_submit_stock_story
from src.worker.stream import ChatRelay, run_chat
from tests.unit.openai_sse import model, openrouter, tool_call
from tests.unit.test_worker_stream import Events, part
from tests.utils import STORY


def thinking(text: str, node: str = "agent", ns: tuple[str, ...] = ()) -> dict[str, Any]:
    chunk = AIMessageChunk(content="", id="m1", additional_kwargs={REASONING: text})
    return part("messages", (chunk, {"langgraph_node": node}), ns)


async def test_only_the_assistant_nodes_reasoning_is_sent():
    events = Events()
    relay = ChatRelay(events)
    await relay.feed(thinking("analyst musing", ns=("tools:1", "analyst:2")))
    await relay.feed(thinking("tool node", node="tools"))
    await relay.feed(thinking("mine"))
    await relay.flush()
    assert events == [("reasoning", {"text": "mine"})]


async def test_tool_call_arguments_are_not_reasoning():
    events = Events()
    call = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[{"name": "recall", "args": '{"q": "x"}', "id": "c1", "index": 0}],
    )
    await ChatRelay(events).feed(part("messages", (call, {"langgraph_node": "agent"})))
    assert events == []


async def test_a_retry_after_reasoning_alone_marks_the_break_without_a_reset():
    events = Events()
    relay = ChatRelay(events)
    await relay.feed(thinking("Let me check the hol"))
    await relay.feed(part("custom", {"event": "retry", "attempt": 2}))
    await relay.feed(thinking("The investor asks"))
    await relay.flush()
    boundary = events.index(
        ("progress", {"stage": "assistant", "detail": progress.ASSISTANT_RETRYING})
    )
    assert "".join(data["text"] for _, data in events[:boundary]) == "Let me check the hol"
    assert "".join(data["text"] for _, data in events[boundary + 1 :]) == "The investor asks"
    assert "reset" not in [kind for kind, _ in events]


async def test_a_research_role_run_inside_a_tool_never_leaks_its_reasoning():
    analyst_model = model(
        ([openrouter("ANALYST SECRET"), tool_call("submit_stock_story", STORY)], "tool_calls")
    )
    role = build_role("analyst", analyst_model, [build_submit_stock_story()], 10)

    @tool
    async def consult() -> str:
        """Runs the analyst."""
        await role("You are the analyst.", "Research MSFT.")
        return "story ready"

    chat_model = model(
        ([openrouter("chat thinks "), tool_call("consult", {})], "tool_calls"),
        ([openrouter("after "), {"content": "Done"}], "stop"),
    )
    bound = llm.with_backoff(chat_model.bind_tools([consult]))

    async def agent(state: MessagesState) -> dict[str, object]:
        return {"messages": [llm.complete(await bound.ainvoke(state["messages"]))]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode([consult]))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    events = Events()

    result = await run_chat(
        graph.compile(checkpointer=InMemorySaver()), "t", "a" * 32, "hi", events
    )

    assert result["reply"] == "Done"
    assert "ANALYST SECRET" not in str(events)
    assert [e for e in events if e[0] == "reasoning"] == [
        ("reasoning", {"text": "chat thinks "}),
        ("reasoning", {"text": "after "}),
    ]
