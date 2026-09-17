"""Single-valued facts: one active value per investor per key, stored as a sentence to embed."""

from dataclasses import dataclass
from typing import Literal

from src.prompts.facts import SENTENCES

Subject = Literal["user", "assistant"]
KeyedKind = Literal["identity", "profile", "signal"]
Source = Literal["chat", "client", "gateway", "voice", "cli", "owner"]


@dataclass(frozen=True)
class Key:
    subject: Subject
    kind: KeyedKind
    # How the value reads as a fact; `{}` is the value.
    sentence: str


KEYS: dict[str, Key] = {
    "bot_name": Key("assistant", "identity", SENTENCES["bot_name"]),
    "analyst_name": Key("assistant", "identity", SENTENCES["analyst_name"]),
    "checker_name": Key("assistant", "identity", SENTENCES["checker_name"]),
    "strategist_name": Key("assistant", "identity", SENTENCES["strategist_name"]),
    "bot_emoji": Key("assistant", "identity", SENTENCES["bot_emoji"]),
    "bot_vibe": Key("assistant", "identity", SENTENCES["bot_vibe"]),
    # Reserved for the voice channel; nothing sets it yet.
    "tts_voice": Key("assistant", "identity", SENTENCES["tts_voice"]),
    "name": Key("user", "profile", SENTENCES["name"]),
    "preferred_name": Key("user", "profile", SENTENCES["preferred_name"]),
    "city": Key("user", "profile", SENTENCES["city"]),
    "country": Key("user", "profile", SENTENCES["country"]),
    "currency": Key("user", "profile", SENTENCES["currency"]),
    "timezone": Key("user", "profile", SENTENCES["timezone"]),
    # Signals are written by code from the request, never by a model tool.
    "ip": Key("user", "signal", SENTENCES["ip"]),
    "client": Key("user", "signal", SENTENCES["client"]),
    "channel": Key("user", "signal", SENTENCES["channel"]),
    "last_seen_city": Key("user", "signal", SENTENCES["last_seen_city"]),
    # Setup steps the investor chose to skip (`graph/setup.py`); kept apart from their profile.
    "setup_team_names": Key("user", "profile", SENTENCES["setup_team_names"]),
    "setup_holdings": Key("user", "profile", SENTENCES["setup_holdings"]),
}

SkippableStep = Literal["team_names", "holdings"]
# Each optional setup step: the fact that marks it skipped and the value it is saved with.
SETUP_SKIPS: dict[str, tuple[str, str]] = {
    "team_names": ("setup_team_names", "declined"),
    "holdings": ("setup_holdings", "none"),
}
SETUP_KEYS = tuple(key for key, _ in SETUP_SKIPS.values())


def keys_of(kind: KeyedKind) -> tuple[str, ...]:
    """The keys of `kind`, setup skips left out: they are not part of any shown block."""
    return tuple(name for name, key in KEYS.items() if key.kind == kind and name not in SETUP_KEYS)
