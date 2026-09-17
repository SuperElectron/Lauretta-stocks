"""The chat history as the model is shown it: every tool call answered, within a window."""

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from src.graph.reasoning import without_reasoning
from src.prompts.assistant import UNFINISHED_TOOL_CALL as UNFINISHED


def answered(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Adds a failure result after any tool call that never got one, drops empty replies, and
    strips the reasoning kept on tool calls before the latest human message (earlier turns).

    A turn that raised mid-tool leaves its tool calls unanswered in the checkpoint, and the
    provider rejects every later request until each call has a result.
    """
    humans = [i for i, message in enumerate(messages) if isinstance(message, HumanMessage)]
    turn_start = humans[-1] if humans else 0
    shown: list[AnyMessage] = []
    for index, message in enumerate(messages):
        if isinstance(message, AIMessage) and not message.tool_calls and not message.text:
            continue
        if isinstance(message, AIMessage) and index < turn_start:
            message = without_reasoning(message)
        shown.append(message)
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        results = set()
        for later in messages[index + 1 :]:
            if not isinstance(later, ToolMessage):
                break
            results.add(later.tool_call_id)
        missing = [call["id"] for call in message.tool_calls if call["id"] not in results]
        shown.extend(ToolMessage(UNFINISHED, tool_call_id=call_id) for call_id in missing)
    return shown


def recent(messages: list[AnyMessage], limit: int) -> list[AnyMessage]:
    """The last `limit` messages, from the first human turn in them.

    A single turn longer than the window keeps what it can, but never opens on a tool result
    cut from its call.
    """
    window = messages[-limit:]
    for index, message in enumerate(window):
        if isinstance(message, HumanMessage):
            return window[index:]
    start = 0
    while start < len(window) and isinstance(window[start], ToolMessage):
        start += 1
    return window[start:]
