"""Single-valued facts: one active value per investor per key, stored as a sentence to embed."""

from dataclasses import dataclass
from typing import Literal

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
    "bot_name": Key("assistant", "identity", "The investor calls the assistant {}."),
    "bot_emoji": Key("assistant", "identity", "The assistant's emoji is {}."),
    "bot_vibe": Key("assistant", "identity", "The assistant's manner is: {}."),
    # Reserved for the voice channel; nothing sets it yet.
    "tts_voice": Key("assistant", "identity", "The assistant speaks with the {} voice."),
    "name": Key("user", "profile", "The investor's name is {}."),
    "preferred_name": Key("user", "profile", "The investor wants to be called {}."),
    "city": Key("user", "profile", "The investor lives in {}."),
    "country": Key("user", "profile", "The investor's country is {}."),
    "currency": Key("user", "profile", "The investor counts money in {}."),
    "timezone": Key("user", "profile", "The investor's timezone is {}."),
    # Signals are written by code from the request, never by a model tool.
    "ip": Key("user", "signal", "Last connected from IP address {}."),
    "client": Key("user", "signal", "Last connected with the {} app."),
    "channel": Key("user", "signal", "Last spoke through the {} channel."),
    "last_seen_city": Key("user", "signal", "Last seen near {}."),
}


def keys_of(kind: KeyedKind) -> tuple[str, ...]:
    return tuple(name for name, key in KEYS.items() if key.kind == kind)
