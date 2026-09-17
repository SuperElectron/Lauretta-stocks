import pytest

from src.api.openai.chunks import Part, State, map_event
from src.prompts.notes import RETRYING, TIMED_OUT

FRESH = State()
STARTED = State(content_sent=True)
THINKING = State(mid_thought=True)


@pytest.mark.parametrize(
    ("state", "event", "data", "parts", "after"),
    [
        (FRESH, "token", {"text": "Hel"}, [Part({"content": "Hel"})], STARTED),
        (FRESH, "reasoning", {"text": " so"}, [Part({"reasoning_content": " so"})], THINKING),
        (STARTED, "reasoning", {"text": "x\n"}, [Part({"reasoning_content": "x\n"})], STARTED),
        (
            THINKING,
            "tool",
            {"name": "get_thesis", "status": "started"},
            [Part({"reasoning_content": "\nConsulting get thesis…\n"})],
            FRESH,
        ),
        (
            THINKING,
            "progress",
            {"stage": "assistant", "detail": "retrying"},
            [Part({"reasoning_content": "\nDesk retrying…\n"})],
            FRESH,
        ),
        (
            FRESH,
            "progress",
            {"stage": "analyst", "detail": "drafting"},
            [Part({"reasoning_content": "Nate (Analyst) drafting…\n"})],
            FRESH,
        ),
        (
            FRESH,
            "progress",
            {"stage": "checker", "detail": "re-checking the numbers", "name": "Sarah"},
            [Part({"reasoning_content": "Sarah (Auditor) re-checking the numbers…\n"})],
            FRESH,
        ),
        (
            FRESH,
            "progress",
            {"stage": "assistant", "detail": "working it", "name": None},
            [Part({"reasoning_content": "The Director working it…\n"})],
            FRESH,
        ),
        (
            FRESH,
            "progress",
            {"stage": "newcomer", "detail": "arriving"},
            [Part({"reasoning_content": "Newcomer arriving…\n"})],
            FRESH,
        ),
        (
            FRESH,
            "tool",
            {"name": "research_stock", "status": "started"},
            [Part({"reasoning_content": "Consulting research stock…\n"})],
            FRESH,
        ),
        (
            STARTED,
            "tool",
            {"name": "get_thesis", "status": "done"},
            [Part({"reasoning_content": "Get thesis answered.\n"})],
            STARTED,
        ),
        (
            FRESH,
            "tool",
            {"name": "recall", "status": "error"},
            [Part({"reasoning_content": "Recall failed.\n"})],
            FRESH,
        ),
        (STARTED, "message_end", {}, [Part({"content": "\n\n"})], STARTED),
        (FRESH, "reset", {}, [], FRESH),
        (STARTED, "reset", {}, [Part({"content": RETRYING})], STARTED),
        (
            FRESH,
            "notice",
            {"text": "A new soul awaits."},
            [Part({"content": "A new soul awaits.\n\n"})],
            STARTED,
        ),
        (STARTED, "notice", {"text": "N."}, [Part({"content": "\n\nN.\n\n"})], STARTED),
        (STARTED, "done", {"result": {}}, [Part({}, "stop")], State(True, True)),
        (FRESH, "timeout", {}, [Part({"content": TIMED_OUT}, "stop")], State(False, True)),
        (
            STARTED,
            "timeout",
            {},
            [Part({"content": "\n\n" + TIMED_OUT}, "stop")],
            State(True, True),
        ),
        (FRESH, "surprise", {"x": 1}, [], FRESH),
    ],
)
def test_each_job_event_maps_to_its_deltas(state, event, data, parts, after):
    assert map_event(state, event, data) == (parts, after)


@pytest.mark.parametrize(("state", "prefix"), [(FRESH, ""), (STARTED, "\n\n")])
def test_an_error_is_a_readable_note_that_stops_and_carries_the_error(state, prefix):
    parts, after = map_event(state, "error", {"code": "THREAD_BUSY", "message": "busy"})

    note = "The desk could not answer: busy."
    assert parts == [
        Part(
            {"content": prefix + note},
            "stop",
            {"message": note, "type": "server_error", "code": "THREAD_BUSY"},
        )
    ]
    assert after.finished
