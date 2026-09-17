from typing import Any

import anthropic
import httpx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from src.graph import llm
from src.graph.pipeline import Team, build_pipeline
from src.worker.stream import ChatRelay, run_chat, run_research
from tests.utils import ADVICE, REVIEW, STORY, Recorder


class Events(list):
    async def __call__(self, event: Any) -> None:
        self.append((event.type, event.model_dump()))


def part(kind: str, data: Any, ns: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": kind, "ns": ns, "data": data}


def token(text: str, node: str = "agent", ns: tuple[str, ...] = ()) -> dict[str, Any]:
    return part("messages", (AIMessageChunk(content=text, id="m1"), {"langgraph_node": node}), ns)


async def test_a_chat_turn_maps_to_tokens_tools_progress_and_notice():
    events = Events()
    relay = ChatRelay(events)
    research_call = AIMessage(
        content="", tool_calls=[{"name": "research_stock", "args": {}, "id": "c1"}]
    )
    parts = [
        part("messages", (HumanMessage("hi"), {"langgraph_node": "context"})),
        part("updates", {"context": {"persona": "..."}}),
        part("updates", {"agent": {"messages": [research_call]}}),
        part("custom", {"event": "progress", "stage": "analyst", "detail": "drafting"}, ("t:1",)),
        token("internal analyst thinking", ns=("tools:1", "analyst:2")),
        part("updates", {"agent": {"messages": [research_call]}}, ("tools:1", "analyst:2")),
        part(
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(content="{}", name="research_stock", tool_call_id="c1"),
                    ]
                }
            },
        ),
        token("Buy"),
        token(" nothing"),
        part("messages", (ToolMessage("x", tool_call_id="c1"), {"langgraph_node": "tools"})),
        part("updates", {"agent": {"messages": [AIMessage(content="Buy nothing")]}}),
        part("custom", {"event": "notice", "text": "Proposed change to my soul"}),
        part("updates", {"notice": None}),
    ]
    for each in parts:
        await relay.feed(each)

    assert events == [
        ("tool", {"name": "research_stock", "status": "started"}),
        ("progress", {"stage": "analyst", "detail": "drafting"}),
        ("tool", {"name": "research_stock", "status": "done"}),
        ("token", {"text": "Buy"}),
        ("token", {"text": " nothing"}),
        ("notice", {"text": "Proposed change to my soul"}),
    ]
    assert relay.reply == "Buy nothing"
    assert relay.notices == ["Proposed change to my soul"]


async def test_a_failed_tool_is_reported_as_an_error():
    events = Events()
    failed = ToolMessage(content="bad", name="get_thesis", tool_call_id="c1", status="error")
    await ChatRelay(events).feed(part("updates", {"tools": {"messages": [failed]}}))
    assert events == [("tool", {"name": "get_thesis", "status": "error"})]


async def test_a_retry_resets_only_when_tokens_were_sent():
    events = Events()
    relay = ChatRelay(events)
    await relay.feed(part("custom", {"event": "retry", "attempt": 2}))
    await relay.feed(token("Hal"))
    await relay.feed(part("custom", {"event": "retry", "attempt": 2}, ("tools:1",)))
    await relay.feed(part("custom", {"event": "retry", "attempt": 3}))
    assert [kind for kind, _ in events] == ["token", "reset"]


class FlakyModel(GenericFakeChatModel):
    """Streams part of a reply, then fails like a dropped connection, once."""

    failed: bool = False

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if not self.failed:
            self.failed = True
            for text in ("Hal", "f"):
                yield ChatGenerationChunk(message=AIMessageChunk(content=text))
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk


async def test_a_real_retry_after_tokens_streams_reset_then_the_new_reply(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    bound = llm.with_backoff(FlakyModel(messages=iter([AIMessage(content="Hello there")])))

    async def agent(state: MessagesState) -> dict[str, object]:
        return {"messages": [await bound.ainvoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    events = Events()

    result = await run_chat(graph.compile(checkpointer=InMemorySaver()), "t1", "hi", events)

    assert events[:3] == [("token", {"text": "Hal"}), ("token", {"text": "f"}), ("reset", {})]
    assert "".join(data["text"] for kind, data in events[3:]) == "Hello there"
    assert result == {"thread_id": "t1", "reply": "Hello there", "notices": []}


@pytest.mark.usefixtures("no_database")
async def test_research_streams_each_stage_then_returns_the_saved_thesis():
    revise = {**REVIEW, "verdict": "revise", "required_changes": ["Fix it"]}
    team = Team(Recorder(STORY, STORY), Recorder(revise, REVIEW), Recorder(ADVICE))
    events = Events()

    result = await run_research(build_pipeline(None, "friend", team, 1), "msft", events)

    assert [data for _, data in events] == [
        {"stage": "analyst", "detail": "drafting"},
        {"stage": "checker", "detail": "reviewing"},
        {"stage": "checker", "detail": "verdict: revise"},
        {"stage": "analyst", "detail": "redrafting (revision 1)"},
        {"stage": "checker", "detail": "reviewing"},
        {"stage": "checker", "detail": "verdict: approve"},
        {"stage": "advisor", "detail": "weighing it against the portfolio"},
        {"stage": "save", "detail": "thesis saved"},
    ]
    assert result["ticker"] == "MSFT" and result["thesis_id"] == "thesis-1"
    assert result["revisions"] == 1 and result["advice"] == ADVICE


async def test_backoff_gives_up_after_its_attempts(monkeypatch):
    calls = []

    class Down:
        async def ainvoke(self, _messages):
            calls.append(1)
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(llm.emit, "retry", lambda _attempt: None)
    with pytest.raises(anthropic.APIConnectionError):
        await llm.with_backoff(Down()).ainvoke([])
    assert len(calls) == llm.RETRY_ATTEMPTS
