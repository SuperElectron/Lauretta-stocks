"""Each agent's system prompt, stitched from the wording in `src/prompts` and this run's blocks.

Assistant order: head, `<rules>` (code), `<soul>`, `<identity>`, `<user>`, `<signals>`,
`<investor>`, `<holdings>`, `<theses>`, `<conversation_summary>`, then this turn's `<research>`,
`<soul_change>`, `<setup>`, `<stage>`.
"""

import json
from datetime import date
from typing import Any

from src.graph.state import Opening, Stage
from src.prompts import analyst, assistant, checker, compaction, strategist
from src.prompts.rules import RULES


def _today() -> str:
    return date.today().strftime("%A %-d %B %Y")


def render_assistant_prompt(
    persona: str,
    context: str,
    setup: str,
    stage: Stage,
    names: dict[str, str],
    soul_change: str = "",
    opening: Opening = "",
    summary: str = "",
    research: str = "",
) -> str:
    """`setup` is the rendered `<setup>` block; `names` the desk's current names by key;
    `opening` adds the first-contact intro or the greeting to the stage."""
    instruction = assistant.STAGE_INSTRUCTION[stage].format(**names)
    if opening:
        instruction += "\n" + assistant.OPENING[opening].format(**names)
    parts = [
        assistant.HEAD.format(today=_today(), **names),
        f"<rules>\n{RULES}\n</rules>",
        persona,
        context,
        compaction.BLOCK.format(summary=summary) if summary else "",
        research,
        soul_change,
        setup,
        f"<stage>{stage}: {instruction}</stage>",
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
                **names,
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
    """The Checker's prompt: the head (warning on the last round), the draft, the last review."""
    last = checker.LAST_ROUND.format(**names) if last_round else ""
    parts = [checker.HEAD.format(ticker=ticker, today=_today(), last_round=last, **names)]
    parts.append(f"<draft>{json.dumps(story)}</draft>")
    if previous_review is not None:
        parts.append(checker.PREVIOUS.format(review=json.dumps(previous_review)))
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
