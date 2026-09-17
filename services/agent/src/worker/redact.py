"""Guards the model's reasoning before it is streamed: it is raw thinking, not a checked answer.

- The identifying signal values (the investor's IP address and last seen place) are replaced
  with `[redacted]` wherever they appear as whole words, in any case. Channel and client names
  ("api", "phone") are left alone: redacting them would mangle ordinary words.
- A piece of reasoning that quotes a prompt block tag (`<signals>`, `</rules>`, `<user id=1>`...)
  is dropped. The tag list is a heuristic: it catches a verbatim quote of the prompt, not a
  paraphrase of it.
- `<think>` and `</think>` are removed: a client that stores reasoning in those tags and resends
  it would otherwise misread where the reasoning ends.

Reasoning arrives in fragments, so text is held back until a whitespace boundary at least as
far back as the longest pattern: a value or tag split across fragments is still caught. A run
with no whitespace is cut anyway once it is `MAX_HOLDS` times that long, before any `<`.
"""

import re
from collections.abc import Iterable
from typing import Any

# Put in place of an identifying value (IP address, place) in the model's streamed reasoning.
REDACTED = "[redacted]"

# The signal keys whose values identify the investor.
IDENTIFYING_SIGNALS = ("ip", "last_seen_city")
BLOCK_TAGS = (
    "signals", "rules", "soul", "investor", "holdings", "user", "identity",
    "theses", "unknown", "setup", "stage", "soul_change",
)  # fmt: skip
# Open or close, with or without attributes.
_TAG = re.compile(rf"</?(?:{'|'.join(BLOCK_TAGS)})(?=[\s>/])")
_LONGEST_TAG = max(len(f"</{tag}>") for tag in BLOCK_TAGS)
_THINK = re.compile(r"</?think>")
# A run with no whitespace is cut once the buffer is this many holds long.
MAX_HOLDS = 4


def identifying_values(rows: Iterable[dict[str, Any]]) -> list[str]:
    """The values to redact, from active facts rows (`facts.persona_rows`)."""
    return [
        str(row["value"])
        for row in rows
        if row["kind"] == "signal" and row["key"] in IDENTIFYING_SIGNALS and row["value"]
    ]


class ReasoningFilter:
    def __init__(self, secrets: Iterable[str]) -> None:
        values = sorted({s for s in secrets if s.strip()}, key=len, reverse=True)
        alternatives = "|".join(re.escape(v) for v in values)
        # Followed by a non-word character; at the very end only once nothing more can come.
        found = re.IGNORECASE
        self._open = re.compile(rf"(?<!\w)(?:{alternatives})(?=\W)", found) if values else None
        self._closed = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", found) if values else None
        self._hold = max([_LONGEST_TAG, *(len(v) for v in values)])
        self._buffer = ""

    def feed(self, text: str) -> str:
        """What can be sent of the reasoning so far; the rest waits for more."""
        self._buffer = self._clean(self._buffer + text, self._open)
        limit = len(self._buffer) - self._hold
        if limit <= 0:
            return ""
        cut = max(self._buffer.rfind(" ", 0, limit), self._buffer.rfind("\n", 0, limit)) + 1
        if cut <= 0 and len(self._buffer) > MAX_HOLDS * self._hold:
            # No whitespace: cut before the held tail, and before a tag that may start near it.
            tag_start = self._buffer.rfind("<", limit - self._hold, limit)
            cut = tag_start if tag_start > 0 else limit
        if cut <= 0:
            return ""
        ready, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self._guard(ready)

    def flush(self) -> str:
        """Everything still held back: the model call ended or was abandoned."""
        ready, self._buffer = self._clean(self._buffer, self._closed), ""
        return self._guard(ready)

    def _clean(self, text: str, secrets: re.Pattern[str] | None) -> str:
        text = _THINK.sub("", text)
        return secrets.sub(REDACTED, text) if secrets else text

    @staticmethod
    def _guard(text: str) -> str:
        return "" if _TAG.search(text) else text
