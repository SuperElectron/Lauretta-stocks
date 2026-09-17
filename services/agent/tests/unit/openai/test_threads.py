"""Which thread a chat app's request lands on, as AnythingLLM sends them."""

from src.api.openai import digests
from src.api.openai.chunks import TIMED_OUT
from src.api.openai.models import ChatRequest
from src.api.openai.threads import remember_answer
from src.queue.models import Done, MessageEnd, Progress, Token, Tool
from tests.unit.openai.conftest import body, chunks

RECORDS_SENT = 20


class ChatApp:
    """A client like AnythingLLM: resends its last 20 prompt and answer records, stores each run
    of reasoning followed by content as a `<think>` block inside the answer, and saves a turn
    only when the answer has text."""

    def __init__(self, client) -> None:
        self.client = client
        self.records: list[tuple[str, str]] = []

    async def say(self, prompt: str) -> str:
        texts = [t for record in self.records[-RECORDS_SENT:] for t in record]
        response = await self.client.post("/v1/chat/completions", json=body(*texts, prompt))
        stored, reasoning, answered = "", "", False
        for frame in chunks(response.text)[:-1]:
            delta = frame["choices"][0]["delta"]
            reasoning += delta.get("reasoning_content", "")
            if delta.get("content"):
                if reasoning:
                    stored, reasoning = f"{stored}<think>{reasoning}</think>", ""
                stored, answered = stored + delta["content"], True
        if answered:
            self.records.append((prompt, stored))
        return stored


async def test_a_long_conversation_stays_on_one_thread_as_its_window_slides(client, worker):
    app = ChatApp(client)
    for turn in range(41):
        await app.say(f"question {turn}")

    assert len(worker.jobs) == 41
    assert len({job.thread_id for job in worker.jobs}) == 1


async def test_conversations_that_open_alike_get_their_own_threads(client, worker):
    worker.reply = lambda job, n: [Token(text=f"answer {n} on {job.thread_id}"), Done(result={})]
    first, second = ChatApp(client), ChatApp(client)
    await first.say("hi")
    await second.say("hi")
    await second.say("what next?")
    await first.say("what next?")
    await second.say("and then?")

    threads = [job.thread_id for job in worker.jobs]
    assert threads[0] != threads[1]
    assert threads[1] == threads[2] == threads[4]
    assert threads[3] == threads[0]


async def test_a_forked_conversation_keeps_its_thread_after_a_tool_call_mid_answer(client, worker):
    worker.reply = lambda _job, n: [
        Progress(stage="assistant", detail="replying"),
        Token(text="Let me check."),
        MessageEnd(),
        Tool(name="research_stock", status="started"),
        Tool(name="research_stock", status="done"),
        Token(text=f"Answer {n}."),
        Done(result={}),
    ]
    older, forked = ChatApp(client), ChatApp(client)
    await older.say("Research MSFT")
    await forked.say("Research MSFT")
    assert "Consulting research stock" in forked.records[0][1].split("</think>")[1]
    await forked.say("And the risks?")
    await forked.say("Thanks")

    threads = [job.thread_id for job in worker.jobs]
    assert threads[0] != threads[1] == threads[2] == threads[3]


async def test_any_known_pair_beats_the_first_message(client, worker, db):
    request = body("hello", "unknown answer", "hi again", "known answer", "next")
    parsed = ChatRequest.model_validate(request)
    db.owners["oa-fork"] = "friend"
    db.aliases[digests.pair_alias("friend", "hi again", "known answer")] = ("oa-fork", "friend")

    await client.post("/v1/chat/completions", json=request)

    assert worker.jobs[0].thread_id == "oa-fork" != digests.first_message_thread("friend", parsed)


async def test_a_fixed_note_alone_is_not_an_alias(db):
    await remember_answer(None, "friend", "oa-t", "hello", f"<think>x</think>{TIMED_OUT}")
    await remember_answer(None, "friend", "oa-t", "hello", "A real answer.")
    assert len(db.aliases) == 1


async def test_a_thread_header_names_the_thread(client, worker):
    headers = {"X-Thread-Id": "phone"}
    await client.post("/v1/chat/completions", json=body("hello"), headers=headers)
    await client.post("/v1/chat/completions", json=body("goodbye"), headers=headers)

    assert worker.jobs[0].thread_id == worker.jobs[1].thread_id


def test_thread_ids_are_namespaced_by_user():
    request = ChatRequest.model_validate(body("hello"))
    assert digests.first_message_thread("friend", request) != digests.first_message_thread(
        "someone", request
    )
    assert digests.header_thread("friend", "phone") != digests.header_thread("someone", "phone")


def test_an_alias_ignores_every_stored_reasoning_block_and_outer_space():
    stored = "<think>\nhmm\n</think>\n\nHello. Checking.\n\n<think>Consulting x…\n</think>Done. "
    assert digests.pair_alias("friend", "hi", stored) == digests.pair_alias(
        "friend", "hi", "Hello. Checking.\n\nDone."
    )
