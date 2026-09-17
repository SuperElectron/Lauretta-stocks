"""The persona as prompt blocks: soul, identity, user profile and signals, built from facts rows.

Rules are not here: they are code (`persona/rules.py`) and render before all of these.
"""

from dataclasses import dataclass
from typing import Any

from src.memory.keys import keys_of
from src.persona.soul import DEFAULT_SOUL

Fields = dict[str, str | None]

# What the assistant is before the investor says otherwise. The name is never defaulted.
IDENTITY_DEFAULTS: Fields = {
    "bot_name": None,
    "bot_emoji": None,
    "bot_vibe": "a sharp desk trader: direct, candid, professional",
    "tts_voice": None,
}
# Shown to the assistant; tts_voice is reserved for the voice channel.
IDENTITY_SHOWN = ("bot_name", "bot_emoji", "bot_vibe")
USER_KEYS = keys_of("profile")
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
    lines = [f"{key}: {values.get(key) or 'not set'}" for key in keys]
    return f"<{tag}>\n" + "\n".join(lines) + f"\n</{tag}>"


def render_signals(signals: dict[str, tuple[str, str]]) -> str:
    lines = [f"{key}: {value} (since {since})" for key, (value, since) in sorted(signals.items())]
    return "<signals>\n" + ("\n".join(lines) or "none") + "\n</signals>"


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


def unnamed(persona: Persona) -> list[str]:
    """What is missing before the assistant and the investor know what to call each other."""
    missing = []
    if not persona.identity.get("bot_name"):
        missing.append("what the investor wants to call you")
    if not persona.user.get("preferred_name"):
        missing.append("what to call the investor")
    return missing
