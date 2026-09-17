"""The one-page research report written by `just research`. `str.format` fields."""

DISCLAIMER = (
    "_Structured research to support your own decision. Not financial advice; "
    "the desk can be wrong and figures should be checked against the filings linked._"
)
NONE = "- none"
NO_DATE = "no date found"
TARGET_WEIGHT = " (target weight {weight:g}%)"

REPORT = """# {ticker} stock story, {today}

**Suggestion: {action}**{target} · Risk: **{verdict}** after {revisions} revision(s) · \
confidence: {confidence}

{disclaimer}

## Story
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

## Risk
{summary}

**Weaknesses**
{weaknesses}

**Data issues**
{data_issues}

## PM
{rationale}

**Portfolio fit:** {portfolio_fit}

**Key risks**
{key_risks}

**What would change this**
{change_my_mind}

**Questions for you**
{questions}
"""
