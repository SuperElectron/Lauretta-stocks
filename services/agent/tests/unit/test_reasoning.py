"""The model's reasoning, from the provider's SSE bytes to job events, and never into the reply."""

import inspect
import json
from dataclasses import replace

import pytest
from fakeredis import FakeAsyncRedis
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import BaseChatOpenAI

from src.errors import EmptyReply, ReplyTruncated
from src.graph import llm
from src.graph.reasoning import REASONING
from src.queue.models import Job
from src.worker import handler as handler_module
from src.worker.stream import run_chat
from tests.unit.openai_sse import model, one_node_chat, reasoning_delta
from tests.unit.test_handler import handler_for
from tests.unit.test_worker_stream import Events


def thought(events: Events) -> str:
    """The reasoning as sent: held back to word boundaries, so in pieces of any size."""
    return "".join(data["text"] for kind, data in events if kind == "reasoning")


THINKING_TURN = [
    reasoning_delta("The investor "),
    reasoning_delta("says hi."),
    {"role": "assistant", "content": "Good"},
    {"content": " day"},
]


def test_the_private_chatopenai_hook_reasoning_relies_on_is_still_there():
    hook = getattr(ChatOpenAI, "_convert_chunk_to_generation_chunk", None)
    assert hook is not None, "langchain-openai removed _convert_chunk_to_generation_chunk"
    params = list(inspect.signature(hook).parameters)
    assert params == ["self", "chunk", "default_chunk_class", "base_generation_info"], (
        f"langchain-openai changed _convert_chunk_to_generation_chunk to {params}"
    )
    assert "self._convert_chunk_to_generation_chunk(" in inspect.getsource(
        BaseChatOpenAI._astream
    ), "BaseChatOpenAI._astream no longer calls _convert_chunk_to_generation_chunk"


async def test_reasoning_streams_before_the_tokens_and_stays_out_of_the_reply():
    graph = one_node_chat(model((THINKING_TURN, "stop")))
    events = Events()

    result = await run_chat(graph, "mat", "t1", "a" * 32, "hi", events)

    kinds = [kind for kind, _ in events]
    assert kinds == ["reasoning"] * (len(kinds) - 2) + ["token", "token"]
    assert thought(events) == "The investor says hi."
    assert result["reply"] == "Good day"
    state = await graph.aget_state({"configurable": {"thread_id": "mat:t1"}})
    stored = state.values["messages"][-1]
    assert stored.text == "Good day" and REASONING not in stored.additional_kwargs
    assert "says hi" not in json.dumps(stored.model_dump())


async def test_vllm_reasoning_content_is_kept_too():
    deltas = [{"role": "assistant", "reasoning_content": "Hmm"}, {"content": "Yes"}]
    events = Events()
    await run_chat(one_node_chat(model((deltas, "stop"))), "mat", "t1", "a" * 32, "hi", events)
    assert events == [("reasoning", {"text": "Hmm"}), ("token", {"text": "Yes"})]


async def test_switched_off_no_reasoning_is_sent():
    events = Events()
    graph = one_node_chat(model((THINKING_TURN, "stop")))
    await run_chat(graph, "mat", "t1", "a" * 32, "hi", events, stream_reasoning=False)
    assert [kind for kind, _ in events] == ["token", "token"]


async def test_signal_values_and_think_tags_never_reach_the_client():
    deltas = [
        reasoning_delta("They came from 100.64."),
        reasoning_delta("0.7 via </think>"),
        reasoning_delta("x"),
    ]
    events = Events()
    graph = one_node_chat(model((deltas + [{"content": "Hi"}], "stop")))
    await run_chat(graph, "mat", "t1", "a" * 32, "hi", events, secrets=["100.64.0.7"])
    assert thought(events) == "They came from [redacted] via x"


async def test_reasoning_counts_toward_the_limit_and_truncation_still_fails_the_turn():
    events = Events()
    graph = one_node_chat(model(([reasoning_delta("Thinking at length")], "length")))
    with pytest.raises(ReplyTruncated):
        await run_chat(graph, "mat", "t1", "a" * 32, "hi", events)
    assert events == [("reasoning", {"text": "Thinking at length"})]


async def test_a_reply_that_only_reasoned_fails_visibly():
    events = Events()
    graph = one_node_chat(model(([reasoning_delta("I wonder")], "stop")))
    with pytest.raises(EmptyReply):
        await run_chat(graph, "mat", "t1", "a" * 32, "hi", events)
    assert thought(events) == "I wonder"


def test_complete_drops_reasoning_but_keeps_the_answer():
    reply = AIMessage("Answer", id="r1", additional_kwargs={REASONING: "why", "other": 1})
    stored = llm.complete(reply)
    assert stored.text == "Answer" and stored.id == "r1"
    assert stored.additional_kwargs == {"other": 1}


def test_an_empty_reply_without_reasoning_is_left_to_the_graph():
    assert llm.complete(AIMessage("")).text == ""


async def test_a_chat_job_guards_reasoning_with_the_signal_values_and_the_setting(monkeypatch):
    seen = {}

    async def run_chat(*_args, secrets, stream_reasoning):
        seen.update(secrets=secrets, stream_reasoning=stream_reasoning)
        return {"reply": "ok"}

    async def signal_values(_user_id):
        return ["100.64.0.7", "phone"]

    monkeypatch.setattr(handler_module, "run_chat", run_chat)
    handler = handler_for(FakeAsyncRedis(decode_responses=True), AGENT_STREAM_REASONING=False)
    handler._app = replace(handler._app, signal_values=signal_values)
    await handler.run(Job(user="mat", kind="chat", message="hi"))

    assert seen == {"secrets": ["100.64.0.7", "phone"], "stream_reasoning": False}
