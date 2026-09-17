"""Every template formats with exactly the fields its code passes: the prompts in `src/prompts`
and the other text kept beside the code that uses it."""

from string import Formatter

import pytest

from src.data.sec import SEC_STATUS, SEC_UNREACHABLE
from src.graph import progress
from src.graph.context import INVESTOR_LINE, THESIS_LINE
from src.graph.role import ROLE_STOPPED
from src.memory.embedder import EMBEDDER_DIMS
from src.memory.keys import KEYS, SENTENCES
from src.persona.approval import SOUL_DECISION, SOUL_PROPOSAL
from src.persona.layers import NAME_KEYS, SIGNAL_LINE
from src.prompts import analyst, assistant, checker, reminders, setup, strategist
from src.queue.consumer import DEAD_UNFINISHED
from src.report import TARGET_WEIGHT

NAMES = set(NAME_KEYS)


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
        (reminders.SUBMIT_REMINDER, {"submit"}),
        (progress.ANALYST_REDRAFTING, {"revision"}),
        (progress.CHECKER_VERDICT, {"verdict"}),
        (SOUL_PROPOSAL, {"short_id", "reason", "content"}),
        (SIGNAL_LINE, {"key", "value", "since"}),
        (INVESTOR_LINE, {"topic", "content", "created", "id"}),
        (THESIS_LINE, {"ticker", "action", "verdict", "created"}),
        (TARGET_WEIGHT, {"weight"}),
        (EMBEDDER_DIMS, {"model", "dims", "expected"}),
        (DEAD_UNFINISHED, {"deliveries"}),
        (ROLE_STOPPED, {"role"}),
        (SEC_STATUS, {"status"}),
        (SEC_UNREACHABLE, {"error"}),
    ],
)
def test_templates_take_exactly_their_fields(template, expected):
    assert fields(template) == expected


def test_every_soul_outcome_formats():
    values = {"verb": "approve", "short_id": "3f2a", "outcome": "x", "reason": "r", "days": 7}
    assert all(t.format(**values) for t in assistant.SOUL_CHANGE.values())
    assert all(fields(t) <= set(values) for t in SOUL_DECISION.values())
    assert set(assistant.SOUL_CHANGE) == set(SOUL_DECISION)


def test_each_fact_sentence_takes_one_value_and_every_key_has_one():
    assert set(SENTENCES) == set(KEYS)
    assert all(sentence.count("{}") == 1 for sentence in SENTENCES.values())


def test_stage_instructions_take_only_the_desk_names():
    assert all(fields(text) <= NAMES for text in assistant.STAGE_INSTRUCTION.values())
    assert all(fields(text) <= NAMES for text in assistant.OPENING.values())
