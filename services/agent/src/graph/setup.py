"""The guided first-run setup: its steps, where the investor is in them and the `<setup>` block.

Decided in code from memory on every turn, never by the model. A step is `done` when memory
shows it, `skipped` when the investor declined an optional one (a `setup_*` fact), else `todo`.
"""

from typing import Any, Literal

from psycopg_pool import AsyncConnectionPool

from src.db.queries import facts, holdings, memories
from src.graph.context import PER_TOPIC, unknown_topics
from src.graph.state import Stage
from src.memory.keys import SETUP_SKIPS
from src.persona.layers import NAME_KEYS, Persona, build_persona
from src.prompts import setup as wording
from src.prompts.identity import IDENTITY_DEFAULTS

SetupStep = Literal["investor_name", "team_names", "core_profile", "holdings"]

# In the order they are offered, with whether the step is required.
STEPS: tuple[tuple[SetupStep, bool], ...] = (
    ("investor_name", True),
    ("team_names", False),
    ("core_profile", True),
    ("holdings", False),
)


def compute_setup(persona: Persona, unknown: list[str], holding_count: int) -> list[dict[str, Any]]:
    """Every step with its status; `missing` lists the core topics still unknown."""
    renamed = any(persona.identity.get(key) != IDENTITY_DEFAULTS[key] for key in NAME_KEYS)
    done = {
        "investor_name": bool(persona.user.get("preferred_name")),
        "team_names": renamed,
        "core_profile": not unknown,
        "holdings": holding_count > 0,
    }
    steps = []
    for step, required in STEPS:
        skip = SETUP_SKIPS.get(step)
        skipped = skip is not None and bool(persona.user.get(skip[0]))
        status = "done" if done[step] else "skipped" if skipped else "todo"
        missing = list(unknown) if step == "core_profile" else []
        steps.append({"step": step, "status": status, "required": required, "missing": missing})
    return steps


async def load_setup(pool: AsyncConnectionPool, user_id: str) -> list[dict[str, Any]]:
    persona = build_persona(await facts.persona_rows(pool, user_id))
    remembered = await memories.by_topic(pool, user_id, PER_TOPIC)
    positions = await holdings.all_of(pool, user_id)
    return compute_setup(persona, unknown_topics(remembered), len(positions))


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
