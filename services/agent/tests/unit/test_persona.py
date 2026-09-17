import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.api.openai.chunks import State, map_event
from src.errors import PersonaInvalid
from src.graph.render import render_assistant_prompt
from src.graph.setup import compute_setup, render_setup
from src.memory.keys import KEYS, keys_of
from src.persona.layers import build_persona, desk_names, render_fields, render_persona
from src.persona.soul import check_soul
from src.prompts.notes import TIMED_OUT, WAITING
from src.prompts.progress import ROLES
from src.prompts.soul import DEFAULT_SOUL, SOUL_MAX_CHARS
from src.tools.persona_args import ProposeSoulArgs, SetIdentityArgs, SetUserDetailsArgs


def keyed(kind: str, key: str, value: str, created: str = "2026-09-16") -> dict:
    content = KEYS[key].sentence.format(value)
    return {"kind": kind, "key": key, "value": value, "content": content, "created": created}


def test_prompt_renders_layers_in_order():
    persona = build_persona([keyed("signal", "channel", "cli")])
    context = "<investor>\nnothing yet\n</investor>\n<holdings>\n</holdings>\n<theses>\n</theses>"
    names = desk_names(persona)
    setup = render_setup(compute_setup(persona, ["goals"], 0), names)
    prompt = render_assistant_prompt(
        render_persona(persona), context, setup, "setup", names,
        "<soul_change>approved 3f2a1b9c: warmer. </soul_change>",
    )  # fmt: skip
    tags = ["<rules>", "<soul>", "<identity>", "<user>", "<signals>", "<investor>", "<holdings>",
            "<theses>", "<soul_change>", "<setup>", "<stage>setup:"]  # fmt: skip
    # Tags open a line; the rules also mention some of them mid-sentence.
    positions = [prompt.index(f"\n{tag}") for tag in tags]
    assert positions == sorted(positions)
    assert "channel: cli (since 2026-09-16)" in prompt


def test_stored_facts_win_over_defaults():
    stored = build_persona(
        [
            keyed("identity", "bot_name", "Ace"),
            {"kind": "soul", "key": None, "value": None, "content": "Terse.", "created": "x"},
        ]
    )
    assert build_persona([]).soul == DEFAULT_SOUL
    assert stored.soul == "Terse." and stored.identity["bot_emoji"] is None
    assert "bot_name: Ace" in render_persona(stored)


COURT = re.compile(
    r"\b(royal|court|inspector|privy|counsellor|chamberlain|sovereign|excellency|treasury|"
    r"grand entrance|sayings)\b",
    re.IGNORECASE,
)
ROOT = Path(__file__).resolve().parents[4]
# The compose network keeps its name: renaming it would recreate the networks.
NETWORK = re.compile(r"`court`|\bcourt:|\[court\b|\bcourt\]")
# The owner's intro paragraph at the top of the README stays word for word.
README_INTRO = range(3, 6)


def test_no_court_theme_in_the_assistant_prompt_or_the_notes():
    persona = build_persona([])
    names = desk_names(persona)
    for current in ("setup", "ready"):
        setup = render_setup(compute_setup(persona, ["goals"], 0), names)
        prompt = render_assistant_prompt(render_persona(persona), "", setup, current, names)
        assert not COURT.search(prompt), COURT.search(prompt)
    error, _ = map_event(State(), "error", {"code": "X", "message": "busy"})
    notes = [*ROLES.values(), TIMED_OUT, WAITING, error[0].delta["content"]]
    assert not [note for note in notes if COURT.search(note)]
    assert set(ROLES.values()) == {"Analyst", "Checker", "Strategist"}


def test_no_court_theme_in_the_wording_readme_or_compose():
    files = [*sorted((ROOT / "services/agent/src/prompts").glob("*.py")), ROOT / "README.md"]
    files.append(ROOT / "docker-compose.yaml")
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for path in files
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if not (path.name == "README.md" and number in README_INTRO)
        and COURT.search(NETWORK.sub("", line))
    ]
    assert hits == []


def test_advisor_user_block_has_no_nickname():
    persona = build_persona([keyed("profile", "preferred_name", "Chief")])
    block = render_fields("user", persona.user, ("name", "country", "currency"))
    assert "Chief" not in block and "currency: not set" in block


def test_soul_is_capped_in_code():
    assert len(DEFAULT_SOUL) <= SOUL_MAX_CHARS
    assert check_soul("  Terse.  ") == "Terse."
    with pytest.raises(PersonaInvalid):
        check_soul("x" * (SOUL_MAX_CHARS + 1))
    with pytest.raises(PersonaInvalid):
        check_soul("   ")
    with pytest.raises(ValidationError):
        ProposeSoulArgs(content="x" * (SOUL_MAX_CHARS + 1), reason="longer")


def test_field_tools_need_at_least_one_value():
    with pytest.raises(ValidationError):
        SetIdentityArgs()
    assert SetUserDetailsArgs(city="Manchester").city == "Manchester"


def test_keys_cover_the_tools_and_signals():
    assert set(keys_of("profile")) == set(SetUserDetailsArgs.model_fields)
    assert set(keys_of("signal")) == {"ip", "client", "channel", "last_seen_city"}
    assert "tts_voice" in keys_of("identity")
    # Setup skips are stored as profile facts but never shown as part of the profile.
    assert KEYS["setup_holdings"].kind == "profile" and "setup_holdings" not in keys_of("profile")
    assert all(key.subject == "assistant" for key in KEYS.values() if key.kind == "identity")
