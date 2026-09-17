"""Test doubles: a scripted chat model and valid role outputs."""

from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolRuntime

from src.graph.ctx import Ctx


class ScriptedModel(GenericFakeChatModel):
    """Replies with the given messages in order; binding tools is a no-op."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # noqa: ARG002
        return self


class Recorder:
    """A role double that returns scripted results and keeps the prompts and contexts it was
    given."""

    def __init__(self, *results: dict[str, Any]) -> None:
        self.results = list(results)
        self.prompts: list[str] = []
        self.contexts: list[Ctx] = []

    async def __call__(self, system_prompt: str, _task: str, context: Ctx) -> dict[str, Any]:
        self.prompts.append(system_prompt)
        self.contexts.append(context)
        return self.results.pop(0)


def runtime_for(user_id: str) -> ToolRuntime:
    """The runtime a ToolNode injects into a tool run for `user_id`."""
    return ToolRuntime(
        state={}, context=Ctx(user_id=user_id), config={}, stream_writer=lambda _chunk: None,
        tool_call_id="call-1", store=None,
    )  # fmt: skip


async def run_as(user_id: str, tool: BaseTool, args: dict[str, Any]) -> Any:
    """Calls `tool` directly, as a run for `user_id` would."""
    return await tool.ainvoke({**args, "runtime": runtime_for(user_id)})


def scripted(*replies: AIMessage) -> ScriptedModel:
    return ScriptedModel(messages=iter(replies))


def call(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


STORY: dict[str, Any] = {
    "business": "Sells software and cloud services to businesses worldwide.",
    "driver": "Cloud revenue growth.",
    "market_gap": "Capex is priced as a permanent margin drag.",
    "catalyst": "Q1 earnings",
    "catalyst_date": "2026-10-28",
    "falsifier": "Cloud growth below 20% in the Q1 report.",
    "risks": ["Capex overruns", "Pricing pressure", "Regulation"],
    "data_snapshot": [
        {"metric": "revenue", "value": "$331.8B", "period": "FY2026", "source": "get_financials"}
    ],
    "data_gaps": ["No segment data"],
    "confidence": "medium",
}

REVIEW: dict[str, Any] = {
    "verdict": "approve",
    "summary": "Cloud growth thesis.",
    "strengths": ["Sourced figures"],
    "weaknesses": [],
    "data_issues": [],
    "missing_information": [],
    "required_changes": [],
}

ADVICE: dict[str, Any] = {
    "action": "watch",
    "target_weight_pct": None,
    "rationale": "Profile unknown.",
    "portfolio_fit": "No holdings recorded.",
    "key_risks": ["Valuation"],
    "change_my_mind": ["Q1 cloud growth above 25%"],
    "questions_for_investor": ["What is your maximum position size?"],
}


def settings(**overrides: Any) -> Any:
    """A valid `Settings` without the environment; overrides replace any field."""
    from src.settings import Settings

    values: dict[str, Any] = {
        "LOG_LEVEL": "INFO",
        "ALLOWED_USERS": "mat,max",
        "DATABASE_URL": "postgresql://unused",
        "DB_POOL_MIN": 1,
        "DB_POOL_MAX": 2,
        "AGENT_PROVIDER": "anthropic",
        "AGENT_MODEL": "claude-test",
        "AGENT_TEMPERATURE": 0.0,
        "AGENT_MAX_TOKENS": 1000,
        "AGENT_TIMEOUT": 30.0,
        "AGENT_RECURSION_LIMIT": 10,
        "PIPELINE_MAX_REVISIONS": 1,
        "EMBED_MODEL": "unused",
        "EMBED_DIMS": 384,
        "SEC_USER_AGENT": "Jo Bloggs jo@example.com",
        "BROKER_URL": "redis://unused",
        **overrides,
    }
    return Settings(**values)
