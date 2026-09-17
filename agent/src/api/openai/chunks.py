"""Job events as OpenAI chat completion deltas: a pure mapping, framed by `stream.py`.

| job event     | delta                                                               |
|---------------|---------------------------------------------------------------------|
| (stream open) | `role: assistant`, sent before any event                            |
| `progress`    | `reasoning_content`: "Royal Analyst drafting…"                      |
| `tool`        | `reasoning_content`: "Consulting research stock…"                   |
| `token`       | `content`                                                           |
| `message_end` | `content` "\\n\\n", so text before a tool call stays readable       |
| `reset`       | nothing before any content; after, a "retrying" note (no rollback) |
| `notice`      | `content`, as its own paragraph                                     |
| `done`        | finish_reason `stop`                                                |
| `error`       | a readable `content` note, finish_reason `stop`, and an `error`     |
| `timeout`     | a closing `content` note, finish_reason `stop`                      |

Anything else is not part of the contract and maps to nothing.
"""

from dataclasses import dataclass, replace
from typing import Any

# The court's titles for the stages a job reports progress from.
TITLES = {
    "assistant": "The Director",
    "analyst": "The Royal Analyst",
    "checker": "The Inspector General",
    "advisor": "The Privy Counsellor",
    "save": "The clerk",
}
RETRYING = "\n\n_(retrying…)_\n\n"
TIMED_OUT = (
    "\n\n_(The court is still at work, but this answer has run as long as a reply may. "
    "Ask again shortly and the finished answer will be read back.)_"
)


@dataclass(frozen=True)
class Part:
    delta: dict[str, str]
    finish_reason: str | None = None
    error: dict[str, str] | None = None


@dataclass(frozen=True)
class State:
    # Content went out, so a retried model call can no longer be hidden from the client.
    content_sent: bool = False
    finished: bool = False


ROLE = Part({"role": "assistant"})
# Clients built on the OpenAI SDKs ignore SSE comments, so a quiet stream sends this instead.
KEEPALIVE = Part({"reasoning_content": ""})


def _content(state: State, text: str) -> tuple[list[Part], State]:
    return [Part({"content": text})], replace(state, content_sent=True)


def _reasoning(line: str) -> list[Part]:
    return [Part({"reasoning_content": line + "\n"})]


def map_event(state: State, event: str, data: dict[str, Any]) -> tuple[list[Part], State]:
    """The deltas one job event becomes, and the state after it."""
    if event == "token":
        return _content(state, data["text"])
    if event == "progress":
        who = TITLES.get(data["stage"], data["stage"].capitalize())
        return _reasoning(f"{who} {data['detail']}…"), state
    if event == "tool":
        name = data["name"].replace("_", " ")
        line = {"started": f"Consulting {name}…", "done": f"{name} answered."}.get(
            data["status"], f"{name} failed."
        )
        return _reasoning(line[0].upper() + line[1:]), state
    if event == "message_end":
        return _content(state, "\n\n")
    if event == "reset":
        return _content(state, RETRYING) if state.content_sent else ([], state)
    if event == "notice":
        return _content(state, ("\n\n" if state.content_sent else "") + data["text"] + "\n\n")
    if event == "done":
        return [Part({}, "stop")], replace(state, finished=True)
    if event == "error":
        note = f"The court could not answer: {data['message']}."
        prefix = "\n\n" if state.content_sent else ""
        error = {"message": note, "type": "server_error", "code": data["code"]}
        return [Part({"content": prefix + note}, "stop", error)], replace(state, finished=True)
    if event == "timeout":
        return [Part({"content": TIMED_OUT}, "stop")], replace(state, finished=True)
    return [], state
