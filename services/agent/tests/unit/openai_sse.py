"""A real `ReasoningChatOpenAI` over the real OpenAI SDK, with only the HTTP transport scripted.

Chunks are shaped as vLLM sends them: `reasoning` in newer releases, `reasoning_content` in older.
"""

import json
from typing import Any

import httpx2
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from src.graph import llm
from src.graph.reasoning import ReasoningChatOpenAI

Turn = tuple[list[dict[str, Any]], str]


def reasoning_delta(reasoning: str) -> dict[str, Any]:
    return {"role": "assistant", "content": "", "reasoning": reasoning}


def tool_call(name: str, args: dict[str, Any], call_id: str = "c1") -> dict[str, Any]:
    function = {"name": name, "arguments": json.dumps(args)}
    return {"tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": function}]}


def sse(deltas: list[dict[str, Any]], finish: str = "stop") -> bytes:
    frames = []
    for i, delta in enumerate(deltas):
        last = i == len(deltas) - 1
        choice = {"index": 0, "delta": delta, "finish_reason": finish if last else None}
        body = {
            "id": "gen-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-oss-120b",
            "choices": [choice],
        }
        frames.append(f"data: {json.dumps(body)}\n\n")
    return ("".join(frames) + "data: [DONE]\n\n").encode()


def completion(deltas: list[dict[str, Any]], finish: str = "stop") -> dict[str, Any]:
    """The same reply as one non-streamed response, as vLLM sends it when `stream` is off."""
    message: dict[str, Any] = {"role": "assistant", "content": ""}
    for delta in deltas:
        message["content"] += delta.get("content") or ""
        if delta.get("reasoning"):
            message["reasoning"] = message.get("reasoning", "") + delta["reasoning"]
        for call in delta.get("tool_calls", []):
            message.setdefault("tool_calls", []).append(
                {k: v for k, v in call.items() if k != "index"}
            )
    choice = {"index": 0, "message": message, "finish_reason": finish}
    return {"id": "gen-1", "object": "chat.completion", "created": 1, "model": "gpt-oss-120b",
            "choices": [choice]}  # fmt: skip


def model(*turns: Turn, requests: list[dict[str, Any]] | None = None) -> ReasoningChatOpenAI:
    """Answers each request with the next turn's deltas and finish reason, and appends each
    request body to `requests` when given."""
    queue = list(turns)

    def reply(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if requests is not None:
            requests.append(body)
        deltas, finish = queue.pop(0)
        if not body.get("stream"):
            return httpx2.Response(200, json=completion(deltas, finish))
        headers = {"content-type": "text/event-stream"}
        return httpx2.Response(200, headers=headers, content=sse(deltas, finish))

    return ReasoningChatOpenAI(
        base_url="http://gateway:3000/v1",
        api_key="internal",
        model="gpt-oss-120b",
        max_retries=0,
        http_async_client=httpx2.AsyncClient(transport=httpx2.MockTransport(reply)),
    )


def one_node_chat(chat_model: Any) -> Any:
    """The chat graph's model node as `graph/chat.py` runs it: backoff, then `complete`."""
    bound = llm.with_backoff(chat_model)

    async def agent(state: MessagesState) -> dict[str, object]:
        return {"messages": [llm.complete(await bound.ainvoke(state["messages"]))]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=InMemorySaver())
