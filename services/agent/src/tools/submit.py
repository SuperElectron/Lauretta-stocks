"""The tools each research role hands its work in with.

Each writes the validated result into the role's state, which ends that role's run.
"""

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from pydantic import BaseModel

from src.tools.models import SubmitAdviceArgs, SubmitReviewArgs, SubmitStoryArgs


def _build_submit(name: str, schema: type[BaseModel], description: str) -> BaseTool:
    async def submit(tool_call_id: str, **fields: Any) -> Command:
        result = schema.model_validate({**fields, "tool_call_id": tool_call_id})
        return Command(
            update={
                "result": result.model_dump(mode="json", exclude={"tool_call_id"}),
                "messages": [ToolMessage("submitted", tool_call_id=tool_call_id)],
            }
        )

    return StructuredTool.from_function(
        coroutine=submit, name=name, description=description, args_schema=schema
    )


def build_submit_stock_story() -> BaseTool:
    return _build_submit(
        "submit_stock_story",
        SubmitStoryArgs,
        "Hand in the finished stock story. Call once, after your research, as your last step.",
    )


def build_submit_review() -> BaseTool:
    return _build_submit(
        "submit_review",
        SubmitReviewArgs,
        "Hand in your review of the draft. Call once, after re-checking, as your last step.",
    )


def build_submit_advice() -> BaseTool:
    return _build_submit(
        "submit_advice", SubmitAdviceArgs, "Hand in your suggestion. Call once, as your last step."
    )
