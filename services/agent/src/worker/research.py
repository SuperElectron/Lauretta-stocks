"""A research job: the team's run for the job's user, its progress relayed as job events."""

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from src.graph.ctx import Ctx
from src.worker.stream import Publish, progress_event


async def run_research(
    pipeline: CompiledStateGraph, user: str, ticker: str, publish: Publish
) -> dict[str, Any]:
    final: dict[str, Any] = {}
    async for part in pipeline.astream(
        {"ticker": ticker.upper()},
        context=Ctx(user_id=user),
        stream_mode=["custom", "values"],
        version="v2",
    ):
        if part["type"] == "values":
            final = part["data"]
        elif part["data"].get("event") == "progress":
            await publish(progress_event(part["data"]))
    fields = ("ticker", "thesis_id", "revisions", "story", "review", "advice", "names")
    return {field: final[field] for field in fields}
