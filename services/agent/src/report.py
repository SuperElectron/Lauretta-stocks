"""Renders a research run as a one-page markdown report; the wording is `prompts/report.py`."""

from datetime import date
from typing import Any

from src.persona.layers import NAME_KEYS
from src.prompts import report as text
from src.prompts.identity import IDENTITY_DEFAULTS


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or text.NONE


def render_report(final: dict[str, Any]) -> str:
    story, review, advice = final["story"], final["review"], final["advice"]
    weight = advice["target_weight_pct"]
    names = {key: IDENTITY_DEFAULTS[key] for key in NAME_KEYS} | final.get("names", {})
    snapshot = "\n".join(
        f"| {p['metric']} | {p['value']} | {p['period']} | {p['source']} |"
        for p in story["data_snapshot"]
    )
    return text.REPORT.format(
        ticker=final["ticker"],
        today=date.today().isoformat(),
        action=advice["action"].upper(),
        target=text.TARGET_WEIGHT.format(weight=weight) if weight else "",
        verdict=review["verdict"],
        revisions=final["revisions"],
        confidence=story["confidence"],
        disclaimer=text.DISCLAIMER,
        **{k: story[k] for k in ("business", "driver", "market_gap", "catalyst", "falsifier")},
        catalyst_date=story["catalyst_date"] or text.NO_DATE,
        risks=_bullets(story["risks"]),
        data_gaps=_bullets(story["data_gaps"]),
        snapshot=snapshot,
        summary=review["summary"],
        weaknesses=_bullets(review["weaknesses"]),
        data_issues=_bullets(review["data_issues"]),
        rationale=advice["rationale"],
        portfolio_fit=advice["portfolio_fit"],
        key_risks=_bullets(advice["key_risks"]),
        change_my_mind=_bullets(advice["change_my_mind"]),
        questions=_bullets(advice["questions_for_investor"]),
        **names,
    )
