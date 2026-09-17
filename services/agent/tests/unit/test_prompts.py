"""All wording lives in `src/prompts`: its templates format as documented, and no prompt-like
text grows back anywhere else."""

import ast
from pathlib import Path
from string import Formatter

import pytest

from src.prompts import analyst, assistant, blocks, notes, pm, progress, report, risk

SRC = Path(__file__).resolve().parents[2] / "src"
# A string this long with a space in it, or text over several lines, reads as wording rather
# than an identifier or a key. Stricter than it needs to be on purpose.
MIN_CHARS = 40
# Text that is not persona wording: SQL and Lua, tool descriptions and tool results (which
# LangChain and the model read beside the tool), and settings and API validation.
ALLOWED = (
    "prompts/",
    "db/queries/",
    "queue/lock.py",
    "tools/",
    "graph/outputs.py",
    "settings.py",
    "queue/models.py",
    "api/events.py",
    "api/openai/models.py",
    "api/openai/routes.py",
)


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        (assistant.HEAD, {"today"}),
        (analyst.HEAD, {"ticker", "today"}),
        (analyst.REVISION, {"story", "changes", "issues"}),
        (analyst.TASK, {"ticker"}),
        (risk.HEAD, {"ticker", "today", "last_round"}),
        (risk.PREVIOUS, {"review"}),
        (risk.LAST_ROUND, set()),
        (risk.TASK, {"ticker"}),
        (pm.HEAD, {"ticker", "today"}),
        (pm.UNKNOWN, {"topics"}),
        (pm.TASK, {"ticker"}),
        (progress.LINE, {"title", "detail"}),
        (progress.ANALYST_REDRAFTING, {"revision"}),
        (progress.RISK_VERDICT, {"verdict"}),
        (notes.ERROR, {"message"}),
        (notes.SOUL_PROPOSAL, {"short_id", "reason", "content"}),
        (blocks.SIGNAL_LINE, {"key", "value", "since"}),
        (blocks.INVESTOR_LINE, {"topic", "content", "created", "id"}),
        (blocks.THESIS_LINE, {"ticker", "action", "verdict", "created"}),
        (report.TARGET_WEIGHT, {"weight"}),
    ],
)
def test_templates_take_exactly_their_fields(template, expected):
    assert fields(template) == expected


def test_every_outcome_and_tool_line_formats():
    values = {"verb": "approve", "short_id": "3f2a", "outcome": "x", "reason": "r", "days": 7}
    assert all(t.format(**values) for t in assistant.SOUL_CHANGE.values())
    assert all(fields(line) == {"name"} for line in progress.TOOL.values())


def test_stage_instructions_have_no_fields():
    assert all(not fields(text) for text in assistant.STAGE_INSTRUCTION.values())


def _wording(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
    }
    return [
        f"{path.relative_to(SRC)}:{node.lineno}: {node.value[:60]!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and ((len(node.value) >= MIN_CHARS and " " in node.value) or "\n" in node.value.strip())
    ]


def test_no_prompt_text_outside_the_prompts_package():
    found = [
        line
        for path in sorted(SRC.rglob("*.py"))
        if not str(path.relative_to(SRC)).startswith(ALLOWED)
        for line in _wording(path)
    ]
    assert found == [], "move this wording into src/prompts:\n" + "\n".join(found)
