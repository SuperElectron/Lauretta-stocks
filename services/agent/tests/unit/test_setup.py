"""The guided setup: steps computed from memory, skips that stop the asking, the block and intro."""

import pytest
from pydantic import ValidationError

from src.db.queries import memories
from src.graph.render import render_assistant_prompt
from src.graph.setup import compute_setup, missing_core, next_step, render_setup, stage
from src.memory.keys import KEYS
from src.memory.topics import CORE_TOPICS
from src.persona.layers import build_persona, desk_names, render_persona
from src.tools.persona import build_set_identity, build_skip_setup_step
from src.tools.persona_args import SetIdentityArgs
from tests.unit.test_desk_names import Embedder, FactsTable
from tests.utils import run_as

CORE = list(CORE_TOPICS)


def fact(kind: str, key: str, value: str) -> dict:
    content = KEYS[key].sentence.format(value)
    return {"kind": kind, "key": key, "value": value, "content": content, "created": "x"}


NAME = fact("profile", "preferred_name", "Boss")
TEAM_DECLINED = fact("profile", "setup_team_names", "skipped")
NO_HOLDINGS = fact("profile", "setup_holdings", "skipped")


def statuses(rows: list[dict], unknown: list[str], holdings: int) -> dict[str, str]:
    return {s["step"]: s["status"] for s in compute_setup(build_persona(rows), unknown, holdings)}


@pytest.mark.parametrize(
    ("rows", "unknown", "holdings", "expected", "step"),
    [
        ([], CORE, 0, ["todo", "todo", "todo", "todo"], "investor_name"),
        ([NAME], CORE, 0, ["done", "todo", "todo", "todo"], "team_names"),
        ([NAME, TEAM_DECLINED], CORE, 0, ["done", "skipped", "todo", "todo"], "core_profile"),
        ([NAME, fact("identity", "checker_name", "Chuck")], ["goals"], 0,
         ["done", "done", "todo", "todo"], "core_profile"),
        ([NAME, TEAM_DECLINED], [], 0, ["done", "skipped", "done", "todo"], "holdings"),
        ([NAME, TEAM_DECLINED, NO_HOLDINGS], [], 0, ["done", "skipped", "done", "skipped"], None),
        ([NAME, TEAM_DECLINED], [], 2, ["done", "skipped", "done", "done"], None),
        # A Director name left by the old onboarding does not mean the team was offered.
        ([NAME, fact("identity", "bot_name", "Ace")], [], 2, ["done", "todo", "done", "done"],
         "team_names"),
    ],
)  # fmt: skip
def test_setup_follows_memory(rows, unknown, holdings, expected, step):
    setup = compute_setup(build_persona(rows), unknown, holdings)
    assert [s["status"] for s in setup] == expected
    assert next_step(setup) == step
    assert stage(setup) == ("ready" if step is None else "setup")
    assert [s["required"] for s in setup] == [True, False, True, False]


def test_the_strategist_reads_missing_core_topics_from_setup():
    assert missing_core(compute_setup(build_persona([NAME]), ["goals", "markets"], 0)) == [
        "goals",
        "markets",
    ]


async def test_a_skip_is_stored_and_never_asked_again():
    table = FactsTable()
    skip = build_skip_setup_step(table, Embedder())
    await run_as("friend", skip, {"step": "team_names"})
    await run_as("friend", skip, {"step": "holdings"})
    rows = [NAME, *table.active()]
    assert statuses(rows, [], 0) == {
        "investor_name": "done", "team_names": "skipped", "core_profile": "done",
        "holdings": "skipped",
    }  # fmt: skip
    assert "setup_holdings" not in render_persona(build_persona(rows))
    assert {r["value"] for r in table.active()} == {"skipped"}


async def test_memory_search_never_returns_setup_skips(monkeypatch):
    seen = {}

    async def fake_rows(_pool, _user_id, sql, params):
        seen.update(sql=sql, params=params)
        return []

    monkeypatch.setattr(memories, "rows", fake_rows)
    await memories.search(None, Embedder(), "friend", "holdings", 5)
    assert "NOT coalesce(key = ANY(%(hidden_keys)s), false)" in seen["sql"]
    assert seen["params"]["hidden_keys"] == ["setup_team_names", "setup_holdings"]


def test_names_are_capped():
    with pytest.raises(ValidationError):
        SetIdentityArgs(checker_name="x" * 41)
    assert SetIdentityArgs(checker_name="x" * 40).checker_name


def test_block_shows_the_checklist_and_one_next_step():
    persona = build_persona([NAME, TEAM_DECLINED])
    block = render_setup(
        compute_setup(persona, ["time_horizon", "markets"], 0), desk_names(persona)
    )
    assert block.startswith("<setup>\n✓ What to call them") and block.endswith("</setup>")
    assert "○ Core profile" in block and "still unknown: time horizon, markets" in block
    assert block.count("Next step") == 1
    assert "Next step (core_profile): Ask about their time horizon" in block

    team = render_setup(compute_setup(build_persona([NAME]), [], 0), desk_names(build_persona([])))
    assert "Offer to rename the team (Andy, Charlie, Sammy and you, the Director)" in team
    done = compute_setup(build_persona([NAME, TEAM_DECLINED, NO_HOLDINGS]), [], 0)
    assert "Setup is complete" in render_setup(done, desk_names(persona))


def test_intro_introduces_the_team_as_the_directors_own_and_starts_setup():
    persona = build_persona([fact("identity", "checker_name", "Chuck")])
    names = desk_names(persona)
    setup = render_setup(compute_setup(persona, CORE, 0), names)
    prompt = render_assistant_prompt(
        render_persona(persona), "", setup, "setup", names, opening="intro"
    )
    for part in ("Here's my team", "**Andy, my analyst**", "**Chuck, my checker**",
                 "**Sammy, my strategist**", "sends Andy's work back", "I'm the Director",
                 "YOUR team", "rather than repeating it word for word", "current names",
                 "rename any of us", "Let's get you set up", "What should I call you?",
                 "never ask more than one question", "ONE step forward per reply",
                 "'call the Checker Max'", "not financial advice"):  # fmt: skip
        assert part in prompt, part
    assert "Charlie" not in prompt


async def test_renaming_only_the_director_closes_the_team_step():
    table = FactsTable()
    await run_as("friend", build_set_identity(table, Embedder()), {"name": "Ace"})
    assert statuses([NAME, *table.active()], CORE, 0)["team_names"] == "done"
    assert table.locks and set(table.scopes) == {"friend"}


async def test_an_emoji_alone_leaves_the_team_step_open():
    table = FactsTable()
    await run_as("friend", build_set_identity(table, Embedder()), {"emoji": "🦊"})
    assert statuses([NAME, *table.active()], CORE, 0)["team_names"] == "todo"
