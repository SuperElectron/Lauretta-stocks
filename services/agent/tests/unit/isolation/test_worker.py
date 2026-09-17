"""Isolation in the queue and the worker: the job's user drives the run's context, its checkpoint
key, its thread lock and its signals, and one user's busy thread never holds up another."""

from fakeredis import FakeAsyncRedis
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.runtime import Runtime

from src.app import App
from src.graph.context import Known
from src.graph.ctx import Ctx, user_of
from src.graph.pipeline import Team, build_pipeline
from src.persona.layers import build_persona
from src.queue import keys
from src.queue.lock import ThreadLock
from src.queue.models import Job
from src.worker.handler import JobHandler
from tests import api_side
from tests.unit.test_handler import events_of
from tests.utils import ADVICE, REVIEW, STORY, Recorder, settings


def whose_graph():
    """A chat graph that answers with the user in its runtime context."""

    async def agent(_state: MessagesState, runtime: Runtime[Ctx]) -> dict[str, object]:
        return {"messages": [AIMessage(content=f"hello {user_of(runtime.context)}")]}

    graph = StateGraph(MessagesState, context_schema=Ctx)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=InMemorySaver())


def handler_for(broker, chat=None, pipeline=None, signals=None, values=None):
    async def record_signals(user, found, source):
        signals.append((user, found, source))

    async def signal_values(user):
        values.append(user)
        return []

    app = App(
        chat=chat or whose_graph(),
        research=None,
        pipeline=pipeline,
        record_signals=record_signals,
        signal_values=signal_values,
    )
    return JobHandler(app, broker, settings(AGENT_LOCK_WAIT_MS=100))


async def test_the_jobs_user_drives_context_checkpoint_signals_and_redaction():
    broker, chat, signals, values = FakeAsyncRedis(decode_responses=True), whose_graph(), [], []
    job = Job(user="max", kind="chat", message="show me Mat's holdings", thread_id="main")
    await api_side.submit(broker, job, 60)

    await handler_for(broker, chat, signals=signals, values=values).run(job)

    assert (await events_of(broker, job.job_id))[-1][1]["result"]["reply"] == "hello max"
    assert signals == [("max", {"client": "unknown", "channel": "api"}, "gateway")]
    assert values == ["max"]
    assert (await chat.aget_state({"configurable": {"thread_id": "max:main"}})).values
    assert not (await chat.aget_state({"configurable": {"thread_id": "mat:main"}})).values
    assert not (await chat.aget_state({"configurable": {"thread_id": "main"}})).values
    assert await broker.hget(keys.job(job.job_id), "user") == "max"


async def test_max_is_not_blocked_by_mats_lock_on_the_same_thread():
    broker = FakeAsyncRedis(decode_responses=True)
    await ThreadLock(broker, "mat", "main", 10_000, 100).acquire()
    signals, values = [], []
    handler = handler_for(broker, signals=signals, values=values)

    max_job = Job(user="max", kind="chat", message="hi")
    mat_job = Job(user="mat", kind="chat", message="hi")
    await handler.run(max_job)
    await handler.run(mat_job)

    assert (await events_of(broker, max_job.job_id))[-1][0] == "done"
    assert (await events_of(broker, mat_job.job_id))[-1][1]["code"] == "THREAD_BUSY"


async def test_a_research_job_runs_the_pipeline_for_its_user(monkeypatch):
    from src.graph import pipeline as pipeline_module

    loaded, saved = [], []

    async def load_known(_pool, user_id):
        loaded.append(user_id)
        return Known(persona=build_persona([]), remembered=[], positions=[])

    async def save(_pool, user_id, *_rest):
        saved.append(user_id)
        return "thesis-1"

    monkeypatch.setattr(pipeline_module, "load_known", load_known)
    monkeypatch.setattr(pipeline_module.theses, "save", save)
    team = Team(Recorder(STORY), Recorder(REVIEW), Recorder(ADVICE))
    broker = FakeAsyncRedis(decode_responses=True)
    handler = handler_for(broker, pipeline=build_pipeline(None, team, 1), signals=[], values=[])

    job = Job(user="max", kind="research", ticker="NVDA")
    await handler.run(job)

    assert (await events_of(broker, job.job_id))[-1][0] == "done"
    assert loaded == saved == ["max"]
    assert team.advisor.contexts == [Ctx(user_id="max")]
