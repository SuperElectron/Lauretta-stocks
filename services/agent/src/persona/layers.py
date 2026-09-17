"""The persona as prompt blocks: soul, identity, user profile and signals, built from facts rows.

Rules are not here: they are code (`prompts/rules.py`) and render before all of these. The soul's
default text is `prompts/soul.py`.
"""

from dataclasses import dataclass
from typing import Any

from src.memory.keys import keys_of
from src.prompts.soul import DEFAULT_SOUL

# Every desk agent has a name the investor can change; the others are the defaults. No emoji.
IDENTITY_DEFAULTS: dict[str, str | None] = {
    "bot_name": "the Director",
    "analyst_name": "Andy",
    "checker_name": "Charlie",
    "strategist_name": "Sammy",
    "bot_emoji": None,
    "bot_vibe": "a sharp desk trader: direct, candid, professional",
    "tts_voice": None,
}

NOT_SET = "not set"
NO_SIGNALS = "none"
SIGNAL_LINE = "{key}: {value} (since {since})"

Fields = dict[str, str | None]

# Each desk agent's name key; every one has a default in `IDENTITY_DEFAULTS`.
NAME_KEYS = ("bot_name", "analyst_name", "checker_name", "strategist_name")
# Whose name a progress line from each graph node carries.
STAGE_NAME_KEYS = {
    "assistant": "bot_name",
    "save": "bot_name",
    "analyst": "analyst_name",
    "checker": "checker_name",
    "advisor": "strategist_name",
}
# Shown to the assistant; tts_voice is reserved for the voice channel.
IDENTITY_SHOWN = (*NAME_KEYS, "bot_emoji", "bot_vibe")
USER_KEYS = keys_of("profile")
# Signals shown to the assistant. The IP address stays in the database and never reaches a prompt.
SIGNALS_SHOWN = tuple(key for key in keys_of("signal") if key != "ip")
# The advisor sizes in the investor's currency and home market; it needs no nickname.
ADVISOR_USER_KEYS = ("name", "country", "currency")


@dataclass(frozen=True)
class Persona:
    soul: str
    identity: Fields
    user: Fields
    # Each signal's value and the date it was last seen to change.
    signals: dict[str, tuple[str, str]]


def build_persona(found: list[dict[str, Any]]) -> Persona:
    """The persona from active facts rows, defaults filling whatever was never set."""
    identity = dict(IDENTITY_DEFAULTS)
    user: Fields = dict.fromkeys(USER_KEYS)
    signals: dict[str, tuple[str, str]] = {}
    soul = DEFAULT_SOUL
    for row in found:
        if row["kind"] == "soul":
            soul = row["content"]
        elif row["kind"] == "identity":
            identity[row["key"]] = row["value"]
        elif row["kind"] == "profile":
            user[row["key"]] = row["value"]
        elif row["kind"] == "signal":
            signals[row["key"]] = (row["value"], row["created"])
    return Persona(soul=soul, identity=identity, user=user, signals=signals)


def render_fields(tag: str, values: Fields, keys: tuple[str, ...]) -> str:
    lines = [f"{key}: {values.get(key) or NOT_SET}" for key in keys]
    return f"<{tag}>\n" + "\n".join(lines) + f"\n</{tag}>"


def render_signals(signals: dict[str, tuple[str, str]]) -> str:
    lines = [
        SIGNAL_LINE.format(key=key, value=value, since=since)
        for key, (value, since) in sorted(signals.items())
        if key in SIGNALS_SHOWN
    ]
    return "<signals>\n" + ("\n".join(lines) or NO_SIGNALS) + "\n</signals>"


def render_persona(persona: Persona) -> str:
    """The `<soul>`, `<identity>`, `<user>` and `<signals>` blocks, in that order."""
    return "\n".join(
        [
            f"<soul>\n{persona.soul}\n</soul>",
            render_fields("identity", persona.identity, IDENTITY_SHOWN),
            render_fields("user", persona.user, USER_KEYS),
            render_signals(persona.signals),
        ]
    )


def desk_names(persona: Persona) -> dict[str, str]:
    """Every desk agent's current name, by name key: the stored one, else the default."""
    return {key: str(persona.identity[key]) for key in NAME_KEYS}


def default_name(stage: str) -> str | None:
    """The default name of the agent behind a graph node, for progress events sent without one."""
    key = STAGE_NAME_KEYS.get(stage)
    return IDENTITY_DEFAULTS[key] if key else None
