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
}


def keys_of(kind: KeyedKind) -> tuple[str, ...]:
    return tuple(name for name, key in KEYS.items() if key.kind == kind)
