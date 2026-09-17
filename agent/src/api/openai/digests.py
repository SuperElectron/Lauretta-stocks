"""The hashes that tie a stateless chat request to the court's threads and jobs.

- `request_key`: the user, the thread header and every message but the system prompt. An SDK
  retry sends the same body, so it names the same key; a real repeat carries a longer or slid
  history, so it names a new one.
- `first_message_thread` and `header_thread`: where a conversation lives before any alias does.
- `pair_alias`: one prompt and its answer, as the client resends them. Clients such as
  AnythingLLM resend a sliding window of past turns, so any answered pair still in the window
  finds the thread after the first message has slid out.
"""

import hashlib
import re

from src.api.openai.models import ChatRequest

THREAD_PREFIX = "oa-"
# A reasoning block some clients store in front of the answer they resend.
_THINK = re.compile(r"^\s*<think>.*?</think>", re.DOTALL)


def _digest(*parts: str) -> str:
    # Length-prefixed, so no two different part lists hash the same bytes.
    joined = "".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


def request_key(user_id: str, request: ChatRequest, header: str | None) -> str:
    flat = [part for role, text in request.transcript() for part in (role, text)]
    return _digest(user_id, "request", header or "", request.model, *flat)


def first_message_thread(user_id: str, request: ChatRequest) -> str:
    return THREAD_PREFIX + _digest(user_id, "first", request.model, request.first_user_text())


def header_thread(user_id: str, header: str) -> str:
    return THREAD_PREFIX + _digest(user_id, "header", header)


def answer_text(answer: str) -> str:
    """The answer as the court sent it: without a stored reasoning block or outer whitespace."""
    return _THINK.sub("", answer, count=1).strip()


def pair_alias(user_id: str, prompt: str, answer: str) -> str:
    return _digest(user_id, "pair", prompt, answer_text(answer))
