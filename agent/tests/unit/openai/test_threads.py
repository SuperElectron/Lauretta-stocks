"""Which thread a chat app's request lands on, as AnythingLLM sends them."""

from src.api.openai import digests
from src.api.openai.models import ChatRequest
from src.queue.models import Done, Token
from tests.unit.openai.conftest import body, content

RECORDS_SENT = 20


class ChatApp:
    """A client like AnythingLLM: resends its last 20 prompt and answer records, stores the
    streamed answer behind a reasoning block, and saves a turn only when the answer has text."""

    def __init__(self, client) -> None:
        self.client = client
        self.records: list[tuple[str, str]] = []

    async def say(self, prompt: str) -> str:
        texts = [t for record in self.records[-RECORDS_SENT:] for t in record]
        response = await self.client.post("/v1/chat/completions", json=body(*texts, prompt))
        answer = content(response.text)
        if answer:
            self.records.append((prompt, f"<think>thinking</think>{answer}"))
        return answer


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


def test_an_alias_ignores_a_stored_reasoning_block_and_outer_space():
    stored = digests.pair_alias("friend", "hi", "<think>\nhmm\n</think>\n\nHello there. ")
    assert stored == digests.pair_alias("friend", "hi", "Hello there.")
