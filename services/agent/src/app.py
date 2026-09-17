"""Builds every dependency once: pool, checkpointer, embedder, data clients, both graphs.

Nothing here is bound to a user. Each run names its user: the graphs through their context
(`Ctx`), signals and redaction values by argument.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from src.data.sec import SecClient
from src.db.checkpointer import build_checkpointer
from src.db.pool import open_pool
from src.db.queries import facts
from src.graph import toolsets
from src.graph.chat import build_chat
from src.graph.ctx import Ctx
from src.graph.llm import build_model
from src.graph.pipeline import Team, build_pipeline
from src.graph.role import build_role
from src.memory.embedder import Embedder
from src.settings import Settings
from src.tools.research import RunResearch
from src.worker.redact import identifying_values


async def _no_signals(_user_id: str) -> list[str]:
    return []


@dataclass(frozen=True)
class App:
    chat: CompiledStateGraph
    research: RunResearch
    # The research team's graph itself, for callers that stream its progress.
    pipeline: CompiledStateGraph
    # Records how a user reached us (channel, client, ip...); only changes are stored.
    record_signals: Callable[[str, dict[str, str | None], facts.Source], Awaitable[None]]
    # A user's identifying signal values (ip, place), kept out of streamed reasoning.
    signal_values: Callable[[str], Awaitable[list[str]]] = _no_signals


@asynccontextmanager
async def open_app(settings: Settings) -> AsyncGenerator[App]:
    async with open_pool(
        settings.DATABASE_URL, min_size=settings.DB_POOL_MIN, max_size=settings.DB_POOL_MAX
    ) as pool:
        checkpointer = await build_checkpointer(pool, settings.DATABASE_OWNER_URL)
        embedder = Embedder(settings.EMBED_MODEL, settings.EMBED_DIMS)
        await embedder.start()
        sec = SecClient(settings.SEC_USER_AGENT)
        model = build_model(settings)
        limit = settings.AGENT_RECURSION_LIMIT

        team = Team(
            analyst=build_role("analyst", model, toolsets.analyst_tools(sec), limit),
            checker=build_role("checker", model, toolsets.checker_tools(sec), limit),
            advisor=build_role("advisor", model, toolsets.advisor_tools(pool, embedder), limit),
        )
        pipeline = build_pipeline(pool, team, settings.PIPELINE_MAX_REVISIONS)

        async def run_research(ticker: str, context: Ctx) -> dict[str, Any]:
            return await pipeline.ainvoke({"ticker": ticker.upper()}, context=context)

        async def record_signals(
            user_id: str, signals: dict[str, str | None], source: facts.Source
        ) -> None:
            await facts.record_signals(pool, embedder, user_id, signals, source)

        tools = toolsets.assistant_tools(pool, embedder, run_research)
        chat = build_chat(pool, checkpointer, tools, model, limit)

        async def signal_values(user_id: str) -> list[str]:
            return identifying_values(await facts.persona_rows(pool, user_id))

        yield App(
            chat=chat,
            research=run_research,
            pipeline=pipeline,
            record_signals=record_signals,
            signal_values=signal_values,
        )
