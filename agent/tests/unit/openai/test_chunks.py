import pytest

from src.api.openai.chunks import RETRYING, TIMED_OUT, Part, State, map_event

FRESH = State()
STARTED = State(content_sent=True)


@pytest.mark.parametrize(
    ("state", "event", "data", "parts", "after"),
    [
        (FRESH, "token", {"text": "Hel"}, [Part({"content": "Hel"})], STARTED),
        (
            FRESH,
            "progress",
            {"stage": "analyst", "detail": "drafting"},
            [Part({"reasoning_content": "The Royal Analyst drafting…\n"})],
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

    note = "The court could not answer: busy."
    assert parts == [
        Part(
            {"content": prefix + note},
            "stop",
            {"message": note, "type": "server_error", "code": "THREAD_BUSY"},
        )
    ]
    assert after.finished
