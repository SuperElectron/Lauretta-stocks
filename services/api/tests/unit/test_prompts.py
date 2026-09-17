"""All wording lives in `src/prompts`: its templates format as documented, and no user-facing
text grows back anywhere else."""

from pathlib import Path
from string import Formatter

import pytest

from src.prompts import errors, names, notes, progress
from tests.unit.wording import wording

SRC = Path(__file__).resolve().parents[2] / "src"
# `file:symbol` (top-level def, class or assignment) whose strings are not wording, and why.
ALLOWED = {
    "api/app.py:create_app": "the FastAPI app title, a product name",
    "api/openai/stream.py:DONE_FRAME": "the SSE end-of-stream frame, protocol",
    "db/pool.py:_SCOPE": "SQL: the transaction's user scope for row-level security",
    "settings.py:Settings": "settings validation, read by the operator at startup",
}


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        (errors.NO_RESEARCH, {"ticker"}),
        (errors.NO_SUCH_MODEL, {"model"}),
        (errors.INVALID_FIELDS, {"fields"}),
        (errors.AUDIO_TOO_LARGE, {"limit"}),
        (notes.ERROR, {"message"}),
        (progress.LINE, {"name", "detail"}),
        (progress.ROLE_LINE, {"name", "role", "detail"}),
    ],
)
def test_templates_take_exactly_their_fields(template, expected):
    assert fields(template) == expected


def test_every_tool_line_formats():
    assert all(fields(line) == {"name"} for line in progress.TOOL.values())


def test_every_role_stage_has_a_default_name():
    assert set(progress.ROLES) <= set(names.NAMES_BY_STAGE)


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
        'raise DeskError("the desk could not do that")',
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
        'raise OpenAIError(400, wording.BODY_NOT_JSON, "invalid_json")',
        'logger.bind(job_id=job_id).info("job.done")',
        'x: str = Field(description="What the model reads about this argument.")',
        'raise DeskError(wording.X.format(keys=", ".join(wrong)))',
    ],
)
def test_the_guard_ignores_code(source):
    assert wording(source) == []
