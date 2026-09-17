"""All wording lives in `src/prompts`: its templates format as documented, and no prompt-like
text grows back anywhere else."""

from pathlib import Path
from string import Formatter

import pytest

from src.memory.keys import KEYS
from src.persona.layers import NAME_KEYS
from src.prompts import (
    analyst,
    assistant,
    blocks,
    checker,
    errors,
    notes,
    progress,
    report,
    setup,
    strategist,
)
from src.prompts.facts import SENTENCES
from tests.unit.wording import wording

NAMES = set(NAME_KEYS)
SRC = Path(__file__).resolve().parents[2] / "src"
# `file:symbol` (top-level def, class or assignment) whose strings are not wording, and why.
ALLOWED = {
    "db/checkpointer.py:_VERSION": "SQL: the checkpoint tables' migration version",
    "db/pool.py:_SCOPE": "SQL: the transaction's user scope for row-level security",
    "graph/render.py:_today": "a strftime pattern",
    "memory/embedder.py:Embedder": "the startup probe text, embedded and never shown",
    "persona/approval.py:_DECISION": "the approval phrase regex; the phrase is shown from notes",
    "queue/lock.py:_REFRESH": "Lua for the thread lock",
    "queue/lock.py:_RELEASE": "Lua for the thread lock",
    "settings.py:Settings": "settings validation, read by the operator at startup",
    "tools/submit.py:build_submit_stock_story": "a tool description, kept with its tool",
    "tools/submit.py:build_submit_review": "a tool description, kept with its tool",
    "tools/submit.py:build_submit_advice": "a tool description, kept with its tool",
}


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        (assistant.HEAD, {"today", *NAMES}),
        (assistant.OPENING["intro"], NAMES),
        (assistant.OPENING["welcome"], set()),
        (setup.NEXT_STEP["team_names"], NAMES),
        (setup.NEXT_STEP["core_profile"], {"topic"}),
        (setup.NEXT, {"step", "instruction"}),
        (setup.MISSING, {"topics"}),
        (analyst.HEAD, {"ticker", "today", "analyst_name", "checker_name", "strategist_name"}),
        (analyst.REVISION, {"story", "changes", "issues", "checker_name"}),
        (analyst.TASK, {"ticker"}),
        (
            checker.HEAD,
            {"ticker", "today", "last_round", "analyst_name", "checker_name", "strategist_name"},
        ),
        (checker.PREVIOUS, {"review"}),
        (checker.LAST_ROUND, {"strategist_name"}),
        (checker.TASK, {"ticker"}),
        (strategist.HEAD, {"ticker", "today", "strategist_name", "checker_name"}),
        (strategist.UNKNOWN, {"topics"}),
        (strategist.TASK, {"ticker"}),
        (progress.LINE, {"name", "detail"}),
        (progress.ROLE_LINE, {"name", "role", "detail"}),
        (progress.ANALYST_REDRAFTING, {"revision"}),
        (progress.CHECKER_VERDICT, {"verdict"}),
        (notes.SOUL_PROPOSAL, {"short_id", "reason", "content"}),
        (blocks.SIGNAL_LINE, {"key", "value", "since"}),
        (blocks.INVESTOR_LINE, {"topic", "content", "created", "id"}),
        (blocks.THESIS_LINE, {"ticker", "action", "verdict", "created"}),
        (report.TARGET_WEIGHT, {"weight"}),
        (errors.EMBEDDER_DIMS, {"model", "dims", "expected"}),
        (errors.DEAD_UNFINISHED, {"deliveries"}),
        (errors.ROLE_STOPPED, {"role"}),
    ],
)
def test_templates_take_exactly_their_fields(template, expected):
    assert fields(template) == expected


def test_every_outcome_and_tool_line_formats():
    values = {"verb": "approve", "short_id": "3f2a", "outcome": "x", "reason": "r", "days": 7}
    assert all(t.format(**values) for t in assistant.SOUL_CHANGE.values())
    assert all(fields(t) <= set(values) for t in notes.SOUL_DECISION.values())
    assert set(assistant.SOUL_CHANGE) == set(notes.SOUL_DECISION)
    assert all(fields(line) == {"name"} for line in progress.TOOL.values())


def test_each_fact_sentence_takes_one_value_and_every_key_has_one():
    assert set(SENTENCES) == set(KEYS)
    assert all(sentence.count("{}") == 1 for sentence in SENTENCES.values())


def test_stage_instructions_take_only_the_desk_names():
    assert all(fields(text) <= NAMES for text in assistant.STAGE_INSTRUCTION.values())
    assert all(fields(text) <= NAMES for text in assistant.OPENING.values())


def test_no_wording_outside_the_prompts_package():
    found = []
    for path in sorted(SRC.rglob("*.py")):
        name = str(path.relative_to(SRC))
        if name.startswith("prompts/"):
            continue
        for line, symbol, text in wording(path.read_text(), sql=name.startswith("db/queries/")):
            if f"{name}:{symbol}" not in ALLOWED:
                found.append(f"{name}:{line} ({symbol}): {text[:60]!r}")
    assert found == [], "move this wording into src/prompts:\n" + "\n".join(found)


def test_every_allowlist_entry_still_matches_something():
    used = set()
    for path in sorted(SRC.rglob("*.py")):
        name = str(path.relative_to(SRC))
        used.update(f"{name}:{symbol}" for _, symbol, _ in wording(path.read_text()))
    assert set(ALLOWED) <= used


@pytest.mark.parametrize(
    "source",
    [
        'note = f"The court could not answer: {x}."',
        'emit.progress("analyst", "grand entrance incoming now")',
        'emit.progress("analyst", f"on {x}")',
        'raise OpenAIError(404, "no such thing", "not_found")',
        'raise HTTPException(404, detail={"code": "X", "message": f"none for {t}"})',
        'label = "a short label"',
    ],
)
def test_the_guard_flags_wording(source):
    assert wording(source)


@pytest.mark.parametrize(
    "source",
    [
        'emit.progress("analyst", detail)',
        'raise OpenAIError(400, wording.BODY_NOT_JSON, "invalid_json")',
        'logger.bind(job_id=job_id).info("job.done")',
        'x: str = Field(description="What the model reads about this argument.")',
        'raise PersonaInvalid(wording.X.format(keys=", ".join(wrong)))',
    ],
)
def test_the_guard_ignores_code(source):
    assert wording(source) == []
