"""The chat model: Claude through the Anthropic API, or any OpenAI-compatible server."""

import asyncio
import random

import anthropic
import httpx
import httpx2
import openai
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable

from src.errors import EmptyReply, ReplyTruncated
from src.graph import emit
from src.graph.reasoning import ReasoningChatOpenAI, reasoning_text, without_reasoning
from src.settings import Settings

# Retried with exponential backoff and jitter. Anything else (bad request, auth) fails at once.
RETRYABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
    # A connection dropped mid-stream. The SDKs use httpx2; httpx is kept for other clients.
    httpx.TransportError,
    httpx2.TransportError,
)


def retryable(exc: BaseException) -> bool:
    """Transient: the errors above, a status error on a stream that had already answered 200
    (the provider failed mid-reply) or a 5xx, and OpenAI's mid-stream `error` event."""
    if isinstance(exc, RETRYABLE_ERRORS):
        return True
    if isinstance(exc, (anthropic.APIStatusError, openai.APIStatusError)):
        return exc.status_code == 200 or exc.status_code >= 500
    # Plain `openai.APIError` (no status) is what its stream raises for an `error` event.
    return type(exc) is openai.APIError


RETRY_ATTEMPTS = 3
RETRY_BASE_SECONDS = 1.0


def build_model(settings: Settings) -> BaseChatModel:
    """The provider reads its own key from the environment (ANTHROPIC_API_KEY, OPENAI_API_KEY)."""
    if settings.AGENT_PROVIDER == "anthropic":
        return ChatAnthropic(
            model=settings.AGENT_MODEL,
            temperature=settings.AGENT_TEMPERATURE,
            max_tokens=settings.AGENT_MAX_TOKENS,
            timeout=settings.AGENT_TIMEOUT,
            max_retries=0,
        )
    # Keeps the reasoning vLLM streams, which plain ChatOpenAI drops.
    return ReasoningChatOpenAI(
        base_url=settings.AGENT_BASE_URL,
        model=settings.AGENT_MODEL,
        temperature=settings.AGENT_TEMPERATURE,
        max_tokens=settings.AGENT_MAX_TOKENS,
        timeout=settings.AGENT_TIMEOUT,
        max_retries=0,
    )


class Backoff:
    """Retries the provider's transient failures; every other error surfaces at once.

    Each retry is announced on the custom stream first (`emit.retry`), so a streaming caller
    can void the tokens the failed attempt already sent.
    """

    def __init__(self, model: Runnable) -> None:
        self._model = model

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        attempt = 1
        while True:
            try:
                return await self._model.ainvoke(messages)
            except Exception as exc:
                if not retryable(exc) or attempt == RETRY_ATTEMPTS:
                    raise
            attempt += 1
            emit.retry(attempt)
            # Exponential with up to a second of jitter: about 1s, then 2s.
            await asyncio.sleep(RETRY_BASE_SECONDS * 2 ** (attempt - 2) + random.random())


def with_backoff(model: Runnable) -> Backoff:
    return Backoff(model)


# How each provider says the reply was cut off by the output limit.
_TRUNCATED = {("finish_reason", "length"), ("stop_reason", "max_tokens")}


def complete(reply: AIMessage) -> AIMessage:
    """The reply, or `ReplyTruncated` when the output limit cut it off (a half-written tool
    call would otherwise look like the model choosing to stop), or `EmptyReply` when it only
    reasoned. The reasoning was streamed as it came and is not the answer, so it is dropped,
    except on a tool call: the model reads it again in the rest of this turn."""
    metadata = reply.response_metadata
    if any(metadata.get(key) == value for key, value in _TRUNCATED):
        raise ReplyTruncated
    if not reply.text and not reply.tool_calls and reasoning_text(reply):
        raise EmptyReply
    return reply if reply.tool_calls else without_reasoning(reply)
