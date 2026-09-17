"""Long threads: durable facts are flushed to memory, then a summary replaces what left the view.
Nothing is deleted, and a failed flush or summary changes nothing."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.graph import emit
from src.graph.compaction import BATCH, build_compact, span, transcript, window_start
from src.graph.ctx import Ctx
from src.graph.render import render_assistant_prompt
from tests.utils import ScriptedModel

WINDOW = 4


@pytest.fixture(autouse=True)
def no_stream(monkeypatch):
    """Outside a streaming run there is no writer to report progress to."""
    monkeypatch.setattr(emit, "progress", lambda *_args: None)


def thread(turns: int) -> list:
    """`turns` exchanges of investor message, tool call, tool result and reply."""
    messages: list = []
    for n in range(turns):
        messages += [
            HumanMessage(f"message {n}"),
            AIMessage("", tool_calls=[{"name": "recall", "args": {}, "id": f"c{n}"}]),
            ToolMessage("{}", tool_call_id=f"c{n}", name="recall"),
            AIMessage(f"reply {n}"),
        ]
    return messages


def structured(name: str, args: dict) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"{name}-1"}])


SUMMARY = {"text": "The investor asked about NVDA and prefers dividend payers over growth."}


def state(messages: list, **extra) -> dict:
    return {"messages": messages, "names": {"bot_name": "the Director"}, "context": "", **extra}


def test_the_window_starts_at_an_investor_message():
    messages = thread(10)
    assert window_start(messages, WINDOW) == len(messages) - WINDOW
    assert isinstance(messages[window_start(messages, WINDOW + 1)], HumanMessage)


def test_nothing_is_compacted_until_a_batch_has_left_the_window():
    short = thread(BATCH // 4)
    assert span(short, 0, WINDOW) is None
    long = thread(BATCH // 4 + 2)
    start, end = span(long, 0, WINDOW)
    assert (start, end) == (0, len(long) - WINDOW)
    assert span(long, end, WINDOW) is None


def test_the_transcript_names_who_said_what():
    text = transcript(thread(1))
    assert text.splitlines() == [
        "Investor: message 0",
        "Desk called recall.",
        "recall returned: {}",
        "Desk: reply 0",
    ]


async def test_compaction_flushes_facts_for_the_runs_user_then_summarises():
    saved = []

    async def remember(user_id, topic, content):
        saved.append((user_id, topic, content))

    fact = {"topic": "preference", "content": "Prefers dividend payers over growth stocks."}
    model = ScriptedModel(
        messages=iter([structured("Flush", {"facts": [fact]}), structured("Summary", SUMMARY)])
    )
    messages = thread(BATCH // 4 + 2)
    update = await build_compact(model, WINDOW, remember, "function_calling")(
        state(messages), SimpleNamespace(context=Ctx("max"))
    )
    assert saved == [("max", "preference", "Prefers dividend payers over growth stocks.")]
    assert update == {"summary": SUMMARY["text"], "summarized": len(messages) - WINDOW}


async def test_a_bad_summary_changes_nothing():
    async def remember(*_args):
        return None

    model = ScriptedModel(
        messages=iter([structured("Flush", {"facts": []}), structured("Summary", {"text": ""})])
    )
    update = await build_compact(model, WINDOW, remember, "function_calling")(
        state(thread(BATCH // 4 + 2), summary="old", summarized=0),
        SimpleNamespace(context=Ctx("max")),
    )
    assert update == {}


async def test_a_short_thread_calls_no_model():
    model = ScriptedModel(messages=iter([]))
    update = await build_compact(model, WINDOW, None, "function_calling")(
        state(thread(2)), SimpleNamespace(context=Ctx("max"))
    )
    assert update == {}


def test_the_summary_is_shown_to_the_assistant_only_when_there_is_one():
    names = {"bot_name": "the Director", "analyst_name": "Andy", "checker_name": "Charlie",
             "strategist_name": "Sammy"}  # fmt: skip
    with_summary = render_assistant_prompt("", "", "", "ready", names, summary="They like NVDA.")
    assert "<conversation_summary>\nThey like NVDA.\n</conversation_summary>" in with_summary
    assert "<conversation_summary>" not in render_assistant_prompt("", "", "", "ready", names)
    assert isinstance(SystemMessage(with_summary), SystemMessage)


async def test_a_model_that_gives_no_answer_changes_nothing():
    class Silent:
        async def ainvoke(self, _prompt):
            return None

    class Model:
        def with_structured_output(self, *_args, **_kwargs):
            return Silent()

    update = await build_compact(Model(), WINDOW, None)(
        state(thread(BATCH // 4 + 2)), SimpleNamespace(context=Ctx("max"))
    )
    assert update == {}
