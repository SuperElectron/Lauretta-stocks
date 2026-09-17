"""Renders a research run as a one-page markdown report."""

from datetime import date
from typing import Any

DISCLAIMER = (
    "_Structured research to support your own decision. Not financial advice; "
    "the team can be wrong and figures should be checked against the filings linked._"
)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- none"


def render_report(final: dict[str, Any]) -> str:
    story, review, advice = final["story"], final["review"], final["advice"]
    weight = advice["target_weight_pct"]
    snapshot = "\n".join(
        f"| {p['metric']} | {p['value']} | {p['period']} | {p['source']} |"
        for p in story["data_snapshot"]
    )
    return f"""# {final["ticker"]} stock story, {date.today().isoformat()}

**Suggestion: {advice["action"].upper()}**{f" (target weight {weight:g}%)" if weight else ""} \
· checker: **{review["verdict"]}** after {final["revisions"]} revision(s) · \
confidence: {story["confidence"]}

{DISCLAIMER}

## Story
- **Business:** {story["business"]}
- **Driver:** {story["driver"]}
- **Market gap:** {story["market_gap"]}
- **Catalyst:** {story["catalyst"]} ({story["catalyst_date"] or "no date found"})
- **Falsifier:** {story["falsifier"]}

**Risks**
{_bullets(story["risks"])}

**Data gaps**
{_bullets(story["data_gaps"])}

| Metric | Value | Period | Source |
|---|---|---|---|
{snapshot}

## Checker
{review["summary"]}

**Weaknesses**
{_bullets(review["weaknesses"])}

**Data issues**
{_bullets(review["data_issues"])}

## Advisor
{advice["rationale"]}

**Portfolio fit:** {advice["portfolio_fit"]}

**Key risks**
{_bullets(advice["key_risks"])}

**What would change this**
{_bullets(advice["change_my_mind"])}

**Questions for you**
{_bullets(advice["questions_for_investor"])}
"""
