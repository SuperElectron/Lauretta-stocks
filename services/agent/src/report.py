"""Renders a research run as a one-page markdown report."""

from datetime import date
from typing import Any

from src.persona.layers import IDENTITY_DEFAULTS, NAME_KEYS

DISCLAIMER = (
    "_Structured research to support your own decision. Not financial advice; "
    "the desk can be wrong and figures should be checked against the filings linked._"
)

NONE = "- none"
NO_DATE = "no date found"
TARGET_WEIGHT = " (target weight {weight:g}%)"

REPORT = """# {ticker} stock story, {today}

**Suggestion: {action}**{target} · Checker ({checker_name}): **{verdict}** after {revisions} \
revision(s) · confidence: {confidence}

{disclaimer}

## Story ({analyst_name}, Analyst)
- **Business:** {business}
- **Driver:** {driver}
- **Market gap:** {market_gap}
- **Catalyst:** {catalyst} ({catalyst_date})
- **Falsifier:** {falsifier}

**Risks**
{risks}

**Data gaps**
{data_gaps}

| Metric | Value | Period | Source |
|---|---|---|---|
{snapshot}

## Checker review ({checker_name})
{summary}

**Weaknesses**
{weaknesses}

**Data issues**
{data_issues}

## Strategist ({strategist_name})
{rationale}

**Portfolio fit:** {portfolio_fit}

**Key risks**
{key_risks}

**What would change this**
{change_my_mind}

**Questions for you**
{questions}
"""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or NONE


def render_report(final: dict[str, Any]) -> str:
    story, review, advice = final["story"], final["review"], final["advice"]
    weight = advice["target_weight_pct"]
    names = {key: IDENTITY_DEFAULTS[key] for key in NAME_KEYS} | final.get("names", {})
    snapshot = "\n".join(
        f"| {p['metric']} | {p['value']} | {p['period']} | {p['source']} |"
        for p in story["data_snapshot"]
    )
    return REPORT.format(
        ticker=final["ticker"],
        today=date.today().isoformat(),
        action=advice["action"].upper(),
        target=TARGET_WEIGHT.format(weight=weight) if weight else "",
        verdict=review["verdict"],
        revisions=final["revisions"],
        confidence=story["confidence"],
        disclaimer=DISCLAIMER,
        **{k: story[k] for k in ("business", "driver", "market_gap", "catalyst", "falsifier")},
        catalyst_date=story["catalyst_date"] or NO_DATE,
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
