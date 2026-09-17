"""A research job: the team's run for the job's user, its progress relayed as job events."""

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from src.graph.ctx import Ctx
from src.worker.stream import Publish, progress_event

# The `done` result of a research job, as `contracts/job_events.v1.json` pins it.
RESULT_FIELDS = ("ticker", "thesis_id", "revisions", "story", "review", "advice", "names")


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
    return {field: final[field] for field in RESULT_FIELDS}
