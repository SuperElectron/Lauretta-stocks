"""Test doubles: a scripted chat model and valid role outputs."""

from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class ScriptedModel(GenericFakeChatModel):
    """Replies with the given messages in order; binding tools is a no-op."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # noqa: ARG002
        return self


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
