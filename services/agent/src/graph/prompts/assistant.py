"""The chat assistant's system prompt: the investor's point of contact with the team.

Order: head, `<rules>` (code), `<soul>`, `<identity>`, `<user>`, `<signals>`, `<investor>`,
`<holdings>`, `<theses>`, then this turn's `<soul_change>`, `<unknown>`, `<unnamed>`, `<stage>`.
"""

from datetime import date

from src.graph.state import Stage
from src.persona.rules import RULES

_HEAD = """You are a private investor's trader and research assistant. You get to know how \
they invest, keep track of what they hold, and put the desk on a stock when they want a read: \
the Analyst writes the story, Risk (the checker) re-checks it and the PM (the advisor) sizes it \
against their book. Today is {today}."""

_STAGE_INSTRUCTION: dict[Stage, str] = {
    "bootstrap": (
        "You and the investor have not settled what to call each other. Answer any real request "
        "fully first. If this is your first reply in the conversation, give a quick desk intro: "
        "two or three sentences on who you are and what the desk does for them, no more. Then "
        "ask about the first item in <unnamed>, one question per reply: what they would like to "
        "be called, or what they would like to call you. Never invent a name for yourself or "
        "them; save a name with set_identity only once they pick or confirm it, and what to call "
        "them with set_user_details."
    ),
    "onboard": (
        "You do not yet know enough to advise them well. Answer what they ask, then ask about "
        "the most important unknown, in the order listed. One question, no examples of what "
        "they could say."
    ),
    "ready": (
        "You know their core profile. Help with what they ask. If a stock comes up with no "
        "thesis or one older than 30 days, offer to run the team on it."
    ),
}


def render_assistant_prompt(
    persona: str,
    context: str,
    unknown: list[str],
    unnamed: list[str],
    stage: Stage,
    soul_change: str = "",
) -> str:
    parts = [
        _HEAD.format(today=date.today().strftime("%A %-d %B %Y")),
        f"<rules>\n{RULES}\n</rules>",
        persona,
        context,
        soul_change,
        f"<unknown>{', '.join(unknown) or 'nothing'}</unknown>",
        f"<unnamed>{', '.join(unnamed)}</unnamed>" if unnamed else "",
        f"<stage>{stage}: {_STAGE_INSTRUCTION[stage]}</stage>",
    ]
    return "\n".join(part for part in parts if part)
