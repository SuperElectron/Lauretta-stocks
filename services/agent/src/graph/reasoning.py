"""The model's own reasoning, kept from an OpenAI-compatible stream.

`ChatOpenAI` reads only the official delta fields, so the reasoning a provider adds is dropped
(langchain-openai 1.6, `_convert_delta_to_message_chunk`). OpenRouter streams it as
`delta.reasoning` (and again, structured, as `reasoning_details`); vLLM as
`delta.reasoning_content`, or `delta.reasoning` in newer releases. This subclass keeps the text
on each chunk as `additional_kwargs["reasoning_content"]`, the key LangChain's own provider
packages use, so a streaming caller can show it apart from the answer.
"""

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

REASONING = "reasoning_content"
# The delta fields that carry reasoning text, first match wins.
_DELTA_FIELDS = ("reasoning", "reasoning_content")


def reasoning_text(message: Any) -> str:
    """The reasoning a message or chunk carries, or ""."""
    if not isinstance(message, AIMessage | AIMessageChunk):
        return ""
    text = message.additional_kwargs.get(REASONING)
    return text if isinstance(text, str) else ""


def without_reasoning(message: AIMessage) -> AIMessage:
    """The message as stored: the reasoning was streamed, it is not part of the answer."""
    if REASONING not in message.additional_kwargs:
        return message
    kept = {k: v for k, v in message.additional_kwargs.items() if k != REASONING}
    return message.model_copy(update={"additional_kwargs": kept})


class ReasoningChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        if generation is None or not choices or not isinstance(generation.message, AIMessageChunk):
            return generation
        delta = choices[0].get("delta") or {}
        for field in _DELTA_FIELDS:
            if isinstance(delta.get(field), str) and delta[field]:
                generation.message.additional_kwargs[REASONING] = delta[field]
                break
        return generation
