"""The chat model: Claude through the Anthropic API, or any OpenAI-compatible server."""

import anthropic
import openai
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from src.errors import ReplyTruncated
from src.settings import Settings

# Retried with exponential backoff and jitter. Anything else (bad request, auth) fails at once.
RETRYABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
RETRY_ATTEMPTS = 3


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
    return ChatOpenAI(
        base_url=settings.AGENT_BASE_URL,
        model=settings.AGENT_MODEL,
        temperature=settings.AGENT_TEMPERATURE,
        max_tokens=settings.AGENT_MAX_TOKENS,
        timeout=settings.AGENT_TIMEOUT,
        max_retries=0,
    )


def with_backoff(model: Runnable) -> Runnable:
    """Retries the provider's transient failures; every other error surfaces at once."""
    return model.with_retry(
        retry_if_exception_type=RETRYABLE_ERRORS,
        stop_after_attempt=RETRY_ATTEMPTS,
        wait_exponential_jitter=True,
    )


# How each provider says the reply was cut off by the output limit.
_TRUNCATED = {("finish_reason", "length"), ("stop_reason", "max_tokens")}


def complete(reply: AIMessage) -> AIMessage:
    """The reply, or `ReplyTruncated` when the output limit cut it off (a half-written tool
    call would otherwise look like the model choosing to stop)."""
    metadata = reply.response_metadata
    if any(metadata.get(key) == value for key, value in _TRUNCATED):
        raise ReplyTruncated
    return reply
