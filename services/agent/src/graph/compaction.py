"""Compaction of long threads: before messages leave the model's window, a silent flush saves
what is durable to memory, then a running summary takes their place in the prompt.

Nothing is deleted: every message stays in the checkpoint. `summarized` counts the messages the
summary covers. A failed flush or summary logs an error and changes nothing, so the next turn
tries again with the same messages; it never loses them or stores a bad summary.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from loguru import logger
from pydantic import BaseModel, Field

from src.graph import emit
from src.graph.ctx import user_of
from src.graph.state import ChatState
from src.memory.topics import Topic
from src.prompts import compaction as wording
from src.prompts import progress

# Compact once this many messages have left the window since the last summary.
BATCH = 20
SUMMARY_WORDS = 300
RESULT_CHARS = 400

# Saves one memory: user id, topic, content (deduplicated by the memories table).
Remember = Callable[[str, str, str], Awaitable[Any]]


class Fact(BaseModel):
    topic: Topic
    content: str = Field(min_length=3, max_length=500)


class Flush(BaseModel):
    """The durable facts the investor stated in these messages; empty when there are none."""

    facts: list[Fact] = Field(max_length=20)


class Summary(BaseModel):
    """The running summary of the conversation so far."""

    text: str = Field(min_length=20, max_length=4_000)


def window_start(messages: list[AnyMessage], window: int) -> int:
    """Where the model's recent window begins: at a human message, as `history.recent` does."""
    start = max(len(messages) - window, 0)
    while start < len(messages) and not isinstance(messages[start], HumanMessage):
        start += 1
    return start


def span(messages: list[AnyMessage], summarized: int, window: int) -> tuple[int, int] | None:
    """The messages to compact now, or None until `BATCH` have left the window."""
    end = window_start(messages, window)
    return (summarized, end) if end - summarized >= BATCH else None


def transcript(messages: list[AnyMessage], with_results: bool = True) -> str:
    """The span as lines. Without results for the flush: tool output (web pages, filings) is
    not the investor speaking and must not be able to plant facts in their memory."""
    lines = []
    for message in messages:
        if isinstance(message, HumanMessage):
            lines.append(wording.INVESTOR.format(text=message.text))
        elif isinstance(message, AIMessage):
            if message.text:
                lines.append(wording.DESK.format(text=message.text))
            lines.extend(wording.CALLED.format(name=call["name"]) for call in message.tool_calls)
        elif isinstance(message, ToolMessage) and with_results:
            text = str(message.content)[:RESULT_CHARS]
            lines.append(wording.RESULT.format(name=message.name or "tool", text=text))
    return "\n".join(lines)


async def _required(model, prompt: str):
    """The structured answer; a model that gave none is a failure, never an empty result."""
    answer = await model.ainvoke(prompt)
    if answer is None:
        raise ValueError(type(model).__name__)
    return answer


def build_compact(
    model: BaseChatModel, window: int, remember: Remember, method: str = "json_schema"
) -> Callable:
    """The chat graph's `compact` node, run at the end of a turn. `json_schema` (vLLM's guided
    decoding): measured on gpt-oss-120b, `function_calling` often returned no summary at all."""
    flush_model = model.with_structured_output(Flush, method=method)
    summary_model = model.with_structured_output(Summary, method=method)

    async def compact(state: ChatState, runtime) -> dict[str, object]:
        messages = state["messages"]
        found = span(messages, state.get("summarized", 0), window)
        if found is None:
            return {}
        user_id: str = user_of(runtime.context)
        start, end = found
        text = transcript(messages[start:end])
        said = transcript(messages[start:end], with_results=False)
        log = logger.bind(user=user_id, start=start, end=end)
        emit.progress("compact", progress.COMPACTING, state["names"]["bot_name"])
        try:
            # The `<investor>` block of this turn: what memory already holds, newest per topic.
            known = state.get("context") or wording.NOTHING_REMEMBERED
            flush = await _required(
                flush_model, wording.FLUSH.format(remembered=known, transcript=said)
            )
            for fact in flush.facts:
                await remember(user_id, fact.topic, fact.content)
            previous = state.get("summary") or wording.NO_PREVIOUS
            prompt = wording.SUMMARY.format(
                previous=previous, transcript=text, max_words=SUMMARY_WORDS
            )
            summary = await _required(summary_model, prompt)
        except Exception:
            log.exception("chat.compaction_failed")
            return {}
        log.bind(flushed=len(flush.facts)).info("chat.compacted")
        return {"summary": summary.text, "summarized": end}

    return compact
