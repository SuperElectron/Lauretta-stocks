"""Research the desk starts: queued, never waited for, and reported once."""

import asyncio
import json
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.graph import chat as chat_module
from src.graph.chat import build_chat
from src.graph.context import Known
from src.graph.ctx import Ctx
from src.graph.research import research_block
from src.persona.layers import build_persona
from src.queue import keys
from src.runs import LocalRuns, QueuedRuns
from src.tools.research import build_check_research, build_start_research
from tests.utils import ScriptedModel, runtime_for

TTL = 60


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)


async def queued_jobs(broker) -> list[dict]:
    entries = await broker.xrange(keys.JOBS)
    return [json.loads(fields[keys.PAYLOAD]) for _id, fields in entries]


async def test_starting_research_queues_a_job_for_that_user_and_returns_at_once(broker):
    runs = QueuedRuns(broker, TTL)

    run = await runs.start("max", "NVDA")

    assert run["ticker"] == "NVDA"
    assert run["status"] == keys.QUEUED
    (job,) = await queued_jobs(broker)
    assert (job["kind"], job["ticker"], job["user"]) == ("research", "NVDA", "max")
    assert job["client"] == {"client": "desk"}
    assert job["job_id"] == run["job_id"]
    status = await broker.hgetall(keys.job(run["job_id"]))
    assert status[keys.STATUS] == keys.QUEUED
    assert status[keys.USER] == "max"


async def test_the_same_ticker_is_not_researched_twice_at_once(broker):
    runs = QueuedRuns(broker, TTL)

    first = await runs.start("mat", "MSFT")
    again = await runs.start("mat", "MSFT")

    assert again == first
    assert len(await queued_jobs(broker)) == 1
    # Another user's run of the same ticker is their own.
    other = await runs.start("max", "MSFT")
    assert other["job_id"] != first["job_id"]


async def test_a_finished_run_is_reported_once_and_then_forgotten(broker):
    runs = QueuedRuns(broker, TTL)
    run = await runs.start("mat", "MSFT")
    await broker.hset(keys.job(run["job_id"]), keys.STATUS, keys.DONE)

    block, reported = await research_block(runs, "mat")

    assert "MSFT" in block and "get_thesis" in block
    assert reported == [["MSFT", run["job_id"]]]
    # Still there until the reply it was reported in exists: a turn that died says it again.
    assert (await research_block(runs, "mat"))[0] == block
    # The notice node forgets what the reply reported.
    await runs.clear("mat", reported)
    assert await research_block(runs, "mat") == ("", [])


async def test_a_running_run_stays_in_the_block(broker):
    runs = QueuedRuns(broker, TTL)
    await runs.start("mat", "MSFT")

    block, reported = await research_block(runs, "mat")

    assert "still on it" in block
    assert reported == []
    assert "still on it" in (await research_block(runs, "mat"))[0]


async def test_a_failed_run_is_reported_as_failed(broker):
    runs = QueuedRuns(broker, TTL)
    run = await runs.start("mat", "MSFT")
    await broker.hset(keys.job(run["job_id"]), keys.STATUS, keys.FAILED)

    block, reported = await research_block(runs, "mat")

    assert "failed" in block
    assert reported == [["MSFT", run["job_id"]]]


async def test_a_run_whose_record_is_gone_is_never_claimed_to_have_finished(broker):
    runs = QueuedRuns(broker, TTL)
    run = await runs.start("mat", "MSFT")
    await broker.delete(keys.job(run["job_id"]))

    block, reported = await research_block(runs, "mat")

    assert "lost track" in block
    assert "finished since your last reply" not in block
    assert reported == [["MSFT", run["job_id"]]]
    # The ticker is free again, so the investor can have it run for real.
    again = await runs.start("mat", "MSFT")
    assert again["status"] == keys.QUEUED
    assert again["job_id"] != run["job_id"]


async def test_the_desk_reports_nothing_when_it_started_nothing(broker):
    assert await research_block(QueuedRuns(broker, TTL), "mat") == ("", [])


async def test_the_start_tool_never_waits_for_the_run(broker):
    tool = build_start_research(QueuedRuns(broker, TTL))

    answer = await tool.ainvoke({"ticker": "msft", "runtime": runtime_for("mat")})

    assert answer["ticker"] == "MSFT"
    assert answer["status"] == keys.QUEUED


async def test_a_second_run_of_a_ticker_never_starts_while_one_is_going(broker):
    runs = QueuedRuns(broker, TTL)

    first, second = await asyncio.gather(runs.start("mat", "MSFT"), runs.start("mat", "MSFT"))

    assert first["job_id"] == second["job_id"]
    queued = [job["job_id"] for job in await queued_jobs(broker)]
    assert queued == [first["job_id"]]


async def test_check_research_answers_with_every_run_of_that_user(broker):
    runs = QueuedRuns(broker, TTL)
    await runs.start("mat", "MSFT")
    await runs.start("max", "NVDA")

    answer = await build_check_research(runs).ainvoke({"runtime": runtime_for("mat")})

    assert [run["ticker"] for run in answer["runs"]] == ["MSFT"]


async def test_the_cli_keeps_every_run_it_started():
    running = asyncio.Event()

    async def research(ticker, _context):
        await running.wait()
        return {"ticker": ticker}

    runs = LocalRuns(research)
    first = await runs.start("mat", "AAA")
    await runs.start("mat", "BBB")
    await runs.clear("mat", [[first["ticker"], first["job_id"]]])
    await runs.start("mat", "CCC")

    assert sorted(run["ticker"] for run in await runs.active("mat")) == ["BBB", "CCC"]
    running.set()
    await runs.drain()


async def test_the_cli_runs_research_in_its_own_process():
    started = asyncio.Event()

    async def research(ticker, context):
        started.set()
        return {"ticker": ticker, "user": context.user_id}

    runs = LocalRuns(research)
    run = await runs.start("mat", "MSFT")

    assert run["status"] == keys.RUNNING
    await started.wait()
    await asyncio.sleep(0)
    assert (await runs.active("mat"))[0]["status"] == keys.DONE
    await runs.clear("mat", [[run["ticker"], run["job_id"]]])
    assert await runs.active("mat") == []


class Recording(ScriptedModel):
    """Keeps the system prompt of every call."""

    prompts: list[str] = []

    def _generate(self, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
        self.prompts.append(messages[0].content)
        return super()._generate(messages, *args, **kwargs)


@pytest.fixture
def no_investor(monkeypatch):
    async def load_known(_pool, _user_id):
        return Known(persona=build_persona([]), remembered=[], positions=[])

    async def theses_block(_pool, _user_id):
        return "<theses>\nnone yet\n</theses>"

    monkeypatch.setattr(chat_module, "load_known", load_known)
    monkeypatch.setattr(chat_module, "theses_block", theses_block)


@pytest.mark.usefixtures("no_investor")
async def test_the_desk_is_told_about_a_finished_run_on_the_next_message(broker):
    runs = QueuedRuns(broker, TTL)
    run = await runs.start("mat", "MSFT")
    await broker.hset(keys.job(run["job_id"]), keys.STATUS, keys.DONE)
    model = Recording(messages=iter([AIMessage("Here it is."), AIMessage("Sure.")]), prompts=[])
    graph = build_chat(None, InMemorySaver(), [], model, 20, runs)
    config = {"configurable": {"thread_id": "t"}}

    await graph.ainvoke({"messages": [HumanMessage("any news?")]}, config, context=Ctx("mat"))
    await graph.ainvoke({"messages": [HumanMessage("thanks")]}, config, context=Ctx("mat"))

    told, later = model.prompts
    assert "<research>\nMSFT" in told
    # Reported once: the thesis itself stays in <theses>.
    assert "<research>\n" not in later


@pytest.mark.usefixtures("no_investor")
async def test_a_reported_run_is_not_reported_again_in_a_new_conversation(broker):
    runs = QueuedRuns(broker, TTL)
    run = await runs.start("mat", "MSFT")
    await broker.hset(keys.job(run["job_id"]), keys.STATUS, keys.DONE)
    model = Recording(messages=iter([AIMessage("Here it is."), AIMessage("Hello.")]), prompts=[])
    graph = build_chat(None, InMemorySaver(), [], model, 20, runs)

    for thread in ("first", "second"):
        await graph.ainvoke(
            {"messages": [HumanMessage("any news?")]},
            {"configurable": {"thread_id": thread}},
            context=Ctx("mat"),
        )

    told, other_thread = model.prompts
    assert "<research>\nMSFT" in told
    assert "<research>\n" not in other_thread


async def test_a_ticker_started_again_in_the_same_turn_keeps_its_new_run(broker):
    runs = QueuedRuns(broker, TTL)
    failed = await runs.start("mat", "MSFT")
    await broker.hset(keys.job(failed["job_id"]), keys.STATUS, keys.FAILED)
    _block, reported = await research_block(runs, "mat")

    # The investor says "try again" in the same turn, before the reply forgets the failed run.
    again = await runs.start("mat", "MSFT")
    await runs.clear("mat", reported)

    assert [run["job_id"] for run in await runs.active("mat")] == [again["job_id"]]
