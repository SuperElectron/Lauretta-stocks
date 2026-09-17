"""Turns LangGraph stream parts (`version="v2"`) into job events.

Chat runs with `subgraphs=True`, so the research team's progress reaches the client from
inside the `research_stock` tool. Only the assistant's own tokens, reasoning and tool steps are
sent: a nested graph's tokens, reasoning and updates (the research roles talking to their tools)
are not. Reasoning is never part of the reply and passes `ReasoningFilter` first (off with
`AGENT_STREAM_REASONING=false`). A retry after reasoning alone needs no `reset`, since nothing
of the answer was sent, but a `progress` line marks where the abandoned thinking stopped.
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.graph.reasoning import reasoning_text
from src.prompts import progress
from src.queue.models import Event, MessageEnd, Notice, Progress, Reasoning, Reset, Token, Tool
from src.worker.redact import ReasoningFilter

Publish = Callable[[Event], Awaitable[None]]
# The chat graph's model node; its tokens are the reply.
ASSISTANT_NODE = "agent"


def progress_event(data: dict[str, Any]) -> Progress:
    return Progress(stage=data["stage"], detail=data["detail"], name=data.get("name"))


class ChatRelay:
    """Publishes one chat turn's events and keeps what the `done` result needs."""

    def __init__(
        self, publish: Publish, secrets: Iterable[str] = (), stream_reasoning: bool = True
    ) -> None:
        self._publish = publish
        self._reasoning = ReasoningFilter(secrets) if stream_reasoning else None
        # Tokens (`_streamed`) or reasoning (`_thought`) were sent for the model call in progress.
        self._streamed = self._thought = False
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

    async def flush(self) -> None:
        """Sends the reasoning still held back; call it before any other event and at the end."""
        if self._reasoning is not None and (text := self._reasoning.flush()):
            await self._publish(Reasoning(text=text))

    async def _custom(self, data: dict[str, Any], nested: bool) -> None:
        event = data.get("event")
        await self.flush()
        if event == "progress":
            await self._publish(progress_event(data))
        elif event == "notice" and not nested:
            self.notices.append(data["text"])
            await self._publish(Notice(text=data["text"]))
        elif event == "retry" and not nested and self._streamed:
            self._streamed = self._thought = False
            await self._publish(Reset())
        elif event == "retry" and not nested and self._thought:
            self._thought = False
            await self._publish(Progress(stage="assistant", detail=progress.ASSISTANT_RETRYING))

    async def _message(self, message: Any, metadata: dict[str, Any]) -> None:
        if metadata.get("langgraph_node") != ASSISTANT_NODE:
            return
        if not isinstance(message, AIMessageChunk):
            return
        if self._reasoning is not None and (reasoning := reasoning_text(message)):
            self._thought = True
            if text := self._reasoning.feed(reasoning):
                await self._publish(Reasoning(text=text))
        if message.text:
            await self.flush()
            self._streamed = True
            await self._publish(Token(text=message.text))

    async def _updates(self, data: dict[str, Any]) -> None:
        await self.flush()
        for node, update in data.items():
            messages = (update or {}).get("messages", [])
            if node == ASSISTANT_NODE and messages:
                if self._streamed and messages[-1].tool_calls:
                    await self._publish(MessageEnd())
                self._streamed = self._thought = False
                self.reply = messages[-1].text
                for call in messages[-1].tool_calls:
                    await self._publish(Tool(name=call["name"], status="started"))
            elif node == "tools":
                for message in messages:
                    if isinstance(message, ToolMessage):
                        status = "error" if message.status == "error" else "done"
                        await self._publish(Tool(name=message.name, status=status))


async def run_chat(
    chat: CompiledStateGraph,
    thread_id: str,
    job_id: str,
    message: str,
    publish: Publish,
    secrets: Iterable[str] = (),
    stream_reasoning: bool = True,
) -> dict[str, Any]:
    relay = ChatRelay(publish, secrets, stream_reasoning)
    try:
        async for part in chat.astream(
            # The job id as the message id: a second run of the job replaces it, never repeats it.
            {"messages": [HumanMessage(message, id=job_id)]},
            {"configurable": {"thread_id": thread_id}},
            stream_mode=["messages", "updates", "custom"],
            subgraphs=True,
            version="v2",
        ):
            await relay.feed(part)
    finally:
        # The thinking before a failure is still shown; the error follows it.
        await relay.flush()
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
            await publish(progress_event(part["data"]))
    fields = ("ticker", "thesis_id", "revisions", "story", "review", "advice", "names")
    return {field: final[field] for field in fields}
