"""The persona as prompt blocks: soul, identity, user profile and signals, built from facts rows.

Rules are not here: they are code (`prompts/rules.py`) and render before all of these. The
wording (defaults, empty states) lives in `src/prompts`.
"""

from dataclasses import dataclass
from typing import Any

from src.memory.keys import keys_of
from src.prompts import blocks
from src.prompts import identity as naming
from src.prompts.soul import DEFAULT_SOUL

Fields = dict[str, str | None]

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
    identity = dict(naming.IDENTITY_DEFAULTS)
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
    lines = [f"{key}: {values.get(key) or blocks.NOT_SET}" for key in keys]
    return f"<{tag}>\n" + "\n".join(lines) + f"\n</{tag}>"


def render_signals(signals: dict[str, tuple[str, str]]) -> str:
    lines = [
        blocks.SIGNAL_LINE.format(key=key, value=value, since=since)
        for key, (value, since) in sorted(signals.items())
    ]
    return "<signals>\n" + ("\n".join(lines) or blocks.NO_SIGNALS) + "\n</signals>"


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
        missing.append(naming.UNNAMED_BOT)
    if not persona.user.get("preferred_name"):
        missing.append(naming.UNNAMED_USER)
    return missing
