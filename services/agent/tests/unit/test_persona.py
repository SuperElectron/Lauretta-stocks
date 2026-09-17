import re

import pytest
from pydantic import ValidationError

from src.api.openai.chunks import TIMED_OUT, TITLES, WAITING, State, map_event
from src.errors import PersonaInvalid
from src.graph.prompts.assistant import render_assistant_prompt
from src.graph.state import stage
from src.memory.keys import KEYS, keys_of
from src.persona.layers import build_persona, render_fields, render_persona, unnamed
from src.persona.soul import DEFAULT_SOUL, SOUL_MAX_CHARS, check_soul
from src.tools.models import ProposeSoulArgs, SetIdentityArgs, SetUserDetailsArgs


def keyed(kind: str, key: str, value: str, created: str = "2026-09-16") -> dict:
    content = KEYS[key].sentence.format(value)
    return {"kind": kind, "key": key, "value": value, "content": content, "created": created}


def test_prompt_renders_layers_in_order():
    persona = build_persona([keyed("signal", "channel", "cli")])
    context = "<investor>\nnothing yet\n</investor>\n<holdings>\n</holdings>\n<theses>\n</theses>"
    prompt = render_assistant_prompt(
        render_persona(persona), context, ["goals"], unnamed(persona), "bootstrap",
        "<soul_change>approved 3f2a1b9c: warmer. </soul_change>",
    )  # fmt: skip
    tags = ["<rules>", "<soul>", "<identity>", "<user>", "<signals>", "<investor>", "<holdings>",
            "<theses>", "<soul_change>", "<unknown>", "<unnamed>", "<stage>bootstrap:"]  # fmt: skip
    # Tags open a line; the rules also mention some of them mid-sentence.
    positions = [prompt.index(f"\n{tag}") for tag in tags]
    assert positions == sorted(positions)
    assert "channel: cli (since 2026-09-16)" in prompt


def test_defaults_leave_both_names_unset_and_stored_facts_win():
    default = build_persona([])
    assert default.soul == DEFAULT_SOUL and default.identity["bot_name"] is None
    assert unnamed(default) == ["what the investor wants to call you", "what to call the investor"]

    stored = build_persona(
        [
            keyed("identity", "bot_name", "Ace"),
            keyed("profile", "preferred_name", "Boss"),
            {"kind": "soul", "key": None, "value": None, "content": "Terse.", "created": "x"},
        ]
    )
    assert stored.soul == "Terse." and stored.identity["bot_emoji"] is None
    assert unnamed(stored) == []
    assert "bot_name: Ace" in render_persona(stored)


COURT = re.compile(
    r"royal|court|inspector|privy|counsellor|chamberlain|sovereign|excellency|treasury|"
    r"grand entrance|sayings|director",
    re.IGNORECASE,
)


def test_no_court_theme_in_the_assistant_prompt_or_the_notes():
    persona = build_persona([])
    for current in ("bootstrap", "onboard", "ready"):
        prompt = render_assistant_prompt(render_persona(persona), "", [], unnamed(persona), current)
        assert not COURT.search(prompt), COURT.search(prompt)
    error, _ = map_event(State(), "error", {"code": "X", "message": "busy"})
    waiting = WAITING.delta["reasoning_content"]
    notes = [*TITLES.values(), TIMED_OUT, waiting, error[0].delta["content"]]
    assert not [note for note in notes if COURT.search(note)]
    assert set(TITLES.values()) >= {"Analyst", "Risk", "PM"}


def test_advisor_user_block_has_no_nickname():
    persona = build_persona([keyed("profile", "preferred_name", "Chief")])
    block = render_fields("user", persona.user, ("name", "country", "currency"))
    assert "Chief" not in block and "currency: not set" in block


@pytest.mark.parametrize(
    ("unknown", "names", "expected"),
    [
        (["goals"], ["what to call the investor"], "bootstrap"),
        ([], ["what the investor wants to call you"], "bootstrap"),
        (["goals"], [], "onboard"),
        ([], [], "ready"),
    ],
)
def test_stage_bootstraps_before_onboarding(unknown, names, expected):
    assert stage(unknown, names) == expected


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
    assert all(key.subject == "assistant" for key in KEYS.values() if key.kind == "identity")
