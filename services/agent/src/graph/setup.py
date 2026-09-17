"""The guided first-run setup: its steps, where the investor is in them and the `<setup>` block.

Decided in code from memory on every turn, never by the model. A step is `done` when memory
shows it, `skipped` when the investor declined an optional one (a `setup_*` fact), else `todo`.
How a thread opens (`opening`) is decided in code too.
"""

from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from src.graph.context import Known, unknown_topics
from src.graph.state import Opening, Stage
from src.memory.keys import ANSWERED, SETUP_SKIPS
from src.persona.layers import IDENTITY_DEFAULTS, Persona
from src.prompts import setup as wording

SetupStep = Literal["investor_name", "team_names", "core_profile", "holdings"]

TEAM_NAME_KEYS = ("analyst_name", "checker_name", "strategist_name")
# In the order they are offered, with whether the step is required.
STEPS: tuple[tuple[SetupStep, bool], ...] = (
    ("investor_name", True),
    ("team_names", False),
    ("core_profile", True),
    ("holdings", False),
)


def compute_setup(persona: Persona, unknown: list[str], holding_count: int) -> list[dict[str, Any]]:
    """Every step with its status; `missing` lists the core topics still unknown."""
    # Only the research team counts: a name for the Director alone, as the old onboarding
    # stored, does not mean the team was offered.
    renamed = any(persona.identity.get(key) != IDENTITY_DEFAULTS[key] for key in TEAM_NAME_KEYS)
    # Any rename through set_identity answers the step, the Director's alone included.
    answered = persona.user.get(SETUP_SKIPS["team_names"]) == ANSWERED
    done = {
        "investor_name": bool(persona.user.get("preferred_name")),
        "team_names": renamed or answered,
        "core_profile": not unknown,
        "holdings": holding_count > 0,
    }
    steps = []
    for step, required in STEPS:
        skip = SETUP_SKIPS.get(step)
        skipped = skip is not None and bool(persona.user.get(skip))
        status = "done" if done[step] else "skipped" if skipped else "todo"
        missing = list(unknown) if step == "core_profile" else []
        steps.append({"step": step, "status": status, "required": required, "missing": missing})
    return steps


def setup_of(known: Known) -> list[dict[str, Any]]:
    """The setup, from what was already read this turn or run."""
    return compute_setup(known.persona, unknown_topics(known.remembered), len(known.positions))


def opening(setup: list[dict[str, Any]], messages: list[AnyMessage]) -> Opening:
    """How this turn opens the thread: "" once the thread has an earlier reply; else "intro"
    while their name is unknown (first contact), or "welcome" (greet them by name, no intro)."""
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    if any(isinstance(m, AIMessage) for m in messages[:last_human]):
        return ""
    name = next(s["status"] for s in setup if s["step"] == "investor_name")
    return "intro" if name == "todo" else "welcome"


def next_step(setup: list[dict[str, Any]]) -> str | None:
    return next((s["step"] for s in setup if s["status"] == "todo"), None)


def stage(setup: list[dict[str, Any]]) -> Stage:
    """Setup until every step is done or skipped, then ready."""
    return "setup" if next_step(setup) else "ready"


def missing_core(setup: list[dict[str, Any]]) -> list[str]:
    """The core topics still unknown; the Strategist will not size while any are."""
    return next(s["missing"] for s in setup if s["step"] == "core_profile")


def _readable(topic: str) -> str:
    return topic.replace("_", " ")


def render_setup(setup: list[dict[str, Any]], names: dict[str, str]) -> str:
    """The checklist, then the one next step and how to take it."""
    lines = []
    for s in setup:
        mark, label = wording.MARKS[s["status"]], wording.LABELS[s["step"]]
        line = wording.STEP_LINE.format(mark=mark, label=label)
        if s["missing"]:
            line += wording.MISSING.format(topics=", ".join(map(_readable, s["missing"])))
        lines.append(line)
    step = next_step(setup)
    if step is None:
        lines.append(wording.COMPLETE)
    else:
        topic = _readable(missing_core(setup)[0]) if step == "core_profile" else ""
        how = wording.NEXT_STEP[step].format(topic=topic, **names)
        lines.append(wording.NEXT.format(step=step, instruction=how))
    return "<setup>\n" + "\n".join(lines) + "\n</setup>"
