"""Each agent's system prompt, stitched from the wording in `src/prompts` and this run's blocks.

Assistant order: head, `<rules>` (code), `<soul>`, `<identity>`, `<user>`, `<signals>`,
`<investor>`, `<holdings>`, `<theses>`, then this turn's `<soul_change>`, `<unknown>`,
`<unnamed>`, `<stage>`.
"""

import json
from datetime import date
from typing import Any

from src.graph.state import Stage
from src.prompts import analyst, assistant, auditor, blocks, strategist
from src.prompts.rules import RULES


def _today() -> str:
    return date.today().strftime("%A %-d %B %Y")


def render_assistant_prompt(
    persona: str,
    context: str,
    unknown: list[str],
    unnamed: list[str],
    stage: Stage,
    names: dict[str, str],
    soul_change: str = "",
) -> str:
    """`names` is the desk's current names by key (`persona.layers.desk_names`)."""
    parts = [
        assistant.HEAD.format(today=_today(), **names),
        f"<rules>\n{RULES}\n</rules>",
        persona,
        context,
        soul_change,
        f"<unknown>{', '.join(unknown) or blocks.NOTHING_UNKNOWN}</unknown>",
        f"<unnamed>{', '.join(unnamed)}</unnamed>" if unnamed else "",
        f"<stage>{stage}: {assistant.STAGE_INSTRUCTION[stage].format(**names)}</stage>",
    ]
    return "\n".join(part for part in parts if part)


def render_analyst_prompt(
    ticker: str, investor: str, previous: dict[str, Any] | None, names: dict[str, str]
) -> str:
    """The head, what we know of the investor for relevance, and the revision if there is one.

    `previous` is the last story and its review, or None on the first draft.
    """
    parts = [analyst.HEAD.format(ticker=ticker, today=_today(), **names), investor]
    if previous is not None:
        review = previous["review"]
        parts.append(
            analyst.REVISION.format(
                story=json.dumps(previous["story"]),
                changes=json.dumps(review["required_changes"]),
                issues=json.dumps(review["data_issues"]),
            )
        )
    return "\n".join(parts)


def render_checker_prompt(
    ticker: str,
    story: dict[str, Any],
    previous_review: dict[str, Any] | None,
    last_round: bool,
    names: dict[str, str],
) -> str:
    """The Auditor's prompt: the head (warning on the last round), the draft, the last review."""
    last = auditor.LAST_ROUND if last_round else ""
    parts = [auditor.HEAD.format(ticker=ticker, today=_today(), last_round=last, **names)]
    parts.append(f"<draft>{json.dumps(story)}</draft>")
    if previous_review is not None:
        parts.append(auditor.PREVIOUS.format(review=json.dumps(previous_review)))
    return "\n".join(parts)


def render_advisor_prompt(
    ticker: str,
    user: str,
    investor: str,
    unknown: list[str],
    story: dict[str, Any],
    review: dict[str, Any],
    names: dict[str, str],
) -> str:
    """The Strategist's prompt: the head, the investor, what is unknown, the story and review."""
    parts = [
        strategist.HEAD.format(ticker=ticker, today=_today(), **names),
        user,
        investor,
        strategist.UNKNOWN.format(topics=", ".join(unknown)) if unknown else "",
        f"<story>{json.dumps(story)}</story>",
        f"<review>{json.dumps(review)}</review>",
    ]
    return "\n".join(part for part in parts if part)
