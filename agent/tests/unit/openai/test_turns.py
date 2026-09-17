"""When a request runs a new turn, and when it attaches to the job it already queued."""

import asyncio

import pytest

from src.api.openai import digests
from src.api.openai.models import ChatRequest
from src.queue.models import Done, Error, Token
from tests.unit.openai.conftest import body, client_for, content


@pytest.mark.usefixtures("db")
async def test_an_sdk_retry_attaches_while_running_and_once_done(broker, worker):
    worker.reply = lambda _job, _n: []
    async with client_for(broker, API_MAX_WAIT_S=1) as client:
        await client.post("/v1/chat/completions", json=body("hello", stream_=False))
        await client.post("/v1/chat/completions", json=body("hello", stream_=False))
        assert len(worker.jobs) == 1
        await worker.answer(worker.jobs[0], [Token(text="Hi"), Done(result={})])
        retried = await client.post("/v1/chat/completions", json=body("hello"))

    assert len(worker.jobs) == 1
    assert content(retried.text) == "Hi"


async def test_identical_requests_at_once_start_one_job(client, worker):
    worker.delay = 0.1
    both = await asyncio.gather(
        *(client.post("/v1/chat/completions", json=body("hello")) for _ in range(2))
    )

    assert len(worker.jobs) == 1
    assert all(content(response.text) == "answer 1" for response in both)


async def test_a_delivered_answer_asked_again_is_a_new_turn(client, worker):
    """A regenerate resends the same body once the answer arrived."""
    history = body("hello", "answer 1", "tell me more")
    first = await client.post("/v1/chat/completions", json=history)
    again = await client.post("/v1/chat/completions", json=history)

    assert len(worker.jobs) == 2
    assert (content(first.text), content(again.text)) == ("answer 1", "answer 2")


async def test_a_resend_after_a_failed_turn_is_a_new_turn(client, worker):
    worker.reply = lambda _job, n: (
        [Error(code="THREAD_BUSY", message="busy")]
        if n == 1
        else [Token(text="ok"), Done(result={})]
    )
    await client.post("/v1/chat/completions", json=body("hello"))
    resent = await client.post("/v1/chat/completions", json=body("hello"))

    assert len(worker.jobs) == 2
    assert content(resent.text) == "ok"


async def test_the_same_opening_in_a_new_conversation_is_a_new_turn(client, worker):
    await client.post("/v1/chat/completions", json=body("hello"))
    await client.post("/v1/chat/completions", json=body("hello"))

    assert len(worker.jobs) == 2
    assert worker.jobs[0].thread_id != worker.jobs[1].thread_id


def window(turn: int, last: str) -> ChatRequest:
    """AnythingLLM's request at `turn`: the last 20 prompt and answer records, then `last`."""
    texts = [t for n in range(max(0, turn - 20), turn) for t in (f"q{n}", f"a{n}")]
    return ChatRequest.model_validate(body(*texts, last))


def test_the_same_words_later_in_a_long_conversation_are_a_new_request():
    at_25, at_30 = window(25, "yes"), window(30, "yes")
    assert digests.request_key("friend", at_25, None) != digests.request_key("friend", at_30, None)
    assert digests.request_key("friend", at_25, None) == digests.request_key(
        "friend", window(25, "yes"), None
    )


def test_the_system_prompt_does_not_change_the_request_key():
    plain = body("hello")
    prompted = body("hello")
    prompted["messages"].insert(0, {"role": "system", "content": "Today is Tuesday."})
    keys = {
        digests.request_key("friend", ChatRequest.model_validate(b), None)
        for b in (plain, prompted)
    }
    assert len(keys) == 1
