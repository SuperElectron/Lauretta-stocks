"""Turns LangGraph stream parts (`version="v2"`) into job events.

Chat runs with `subgraphs=True`, so the research team's progress reaches the client from
inside the `research_stock` tool. Only the assistant's own tokens and tool steps are sent: a
nested graph's tokens and updates (the research roles talking to their tools) are not.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.queue.models import Event, Notice, Progress, Reset, Token, Tool

Publish = Callable[[Event], Awaitable[None]]
# The chat graph's model node; its tokens are the reply.
ASSISTANT_NODE = "agent"


class ChatRelay:
    """Publishes one chat turn's events and keeps what the `done` result needs."""

    def __init__(self, publish: Publish) -> None:
        self._publish = publish
        # Tokens were sent for the assistant's model call still in progress.
        self._streamed = False
        self.reply = ""
        self.notices: list[str] = []

    async def feed(self, part: dict[str, Any]) -> None:
        kind, ns, data = part["type"], part["ns"], part["data"]
        if kind == "custom":
            await self._custom(data, nested=bool(ns))
        elif ns:
            return
        elif kind == "messages":
            await self._message(*data)
        elif kind == "updates":
            await self._updates(data)

    async def _custom(self, data: dict[str, Any], nested: bool) -> None:
        event = data.get("event")
        if event == "progress":
            await self._publish(Progress(stage=data["stage"], detail=data["detail"]))
        elif event == "notice" and not nested:
            self.notices.append(data["text"])
            await self._publish(Notice(text=data["text"]))
        elif event == "retry" and not nested and self._streamed:
            self._streamed = False
            await self._publish(Reset())

    async def _message(self, message: Any, metadata: dict[str, Any]) -> None:
        if metadata.get("langgraph_node") != ASSISTANT_NODE:
            return
        if isinstance(message, AIMessageChunk) and message.text:
            self._streamed = True
            await self._publish(Token(text=message.text))

    async def _updates(self, data: dict[str, Any]) -> None:
        for node, update in data.items():
            messages = (update or {}).get("messages", [])
            if node == ASSISTANT_NODE and messages:
                self._streamed = False
                self.reply = messages[-1].text
                for call in messages[-1].tool_calls:
                    await self._publish(Tool(name=call["name"], status="started"))
            elif node == "tools":
                for message in messages:
                    if isinstance(message, ToolMessage):
                        status = "error" if message.status == "error" else "done"
                        await self._publish(Tool(name=message.name, status=status))


async def run_chat(
    chat: CompiledStateGraph, thread_id: str, message: str, publish: Publish
) -> dict[str, Any]:
    relay = ChatRelay(publish)
    async for part in chat.astream(
        {"messages": [HumanMessage(message)]},
        {"configurable": {"thread_id": thread_id}},
        stream_mode=["messages", "updates", "custom"],
        subgraphs=True,
        version="v2",
    ):
        await relay.feed(part)
    return {"thread_id": thread_id, "reply": relay.reply, "notices": relay.notices}


async def run_research(
    pipeline: CompiledStateGraph, ticker: str, publish: Publish
) -> dict[str, Any]:
    final: dict[str, Any] = {}
    async for part in pipeline.astream(
        {"ticker": ticker.upper()}, stream_mode=["custom", "values"], version="v2"
    ):
        if part["type"] == "values":
            final = part["data"]
        elif part["data"].get("event") == "progress":
            await publish(Progress(stage=part["data"]["stage"], detail=part["data"]["detail"]))
    fields = ("ticker", "thesis_id", "revisions", "story", "review", "advice")
    return {field: final[field] for field in fields}
