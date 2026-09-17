"""The model's own reasoning, kept from an OpenAI-compatible stream.

`ChatOpenAI` reads only the official delta fields, so the reasoning a provider adds is dropped
(langchain-openai 1.6, `_convert_delta_to_message_chunk`). vLLM streams it as
`delta.reasoning_content`, or `delta.reasoning` in newer releases (and `message.reasoning` when
not streaming, as a research job or the CLI calls it). This subclass keeps the text on each chunk
or message as `additional_kwargs["reasoning_content"]`, the key LangChain's own provider
packages use, so a streaming caller can show it apart from the answer.

Within one turn the reasoning on a tool-calling reply goes back to the model, as the `reasoning`
field of that assistant message (the field vLLM's gpt-oss harmony parser reads; it ignores the
deprecated `reasoning_content`), so gpt-oss continues its plan instead of re-reasoning after each
tool result. `history.answered` strips it from earlier turns.
"""

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

REASONING = "reasoning_content"
# The delta (or message) fields that carry reasoning text, first match wins.
_DELTA_FIELDS = ("reasoning", "reasoning_content")
# The assistant message field the reasoning is sent back in.
REQUEST_FIELD = "reasoning"


def reasoning_text(message: Any) -> str:
    """The reasoning a message or chunk carries, or ""."""
    if not isinstance(message, AIMessage | AIMessageChunk):
        return ""
    text = message.additional_kwargs.get(REASONING)
    return text if isinstance(text, str) else ""


def _keep(fields: dict, message: AIMessage) -> None:
    """Copies the provider's reasoning field onto the message or chunk."""
    for field in _DELTA_FIELDS:
        if isinstance(fields.get(field), str) and fields[field]:
            message.additional_kwargs[REASONING] = fields[field]
            return


def without_reasoning(message: AIMessage) -> AIMessage:
    """The message without its reasoning: an answer, or a tool call from an earlier turn."""
    if REASONING not in message.additional_kwargs:
        return message
    kept = {k: v for k, v in message.additional_kwargs.items() if k != REASONING}
    return message.model_copy(update={"additional_kwargs": kept})


class ReasoningChatOpenAI(ChatOpenAI):
    def _get_request_payload(
        self, input_: LanguageModelInput, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        sent = payload.get("messages")
        if sent is None:
            return payload
        # Chat Completions keeps one dict per message, in order.
        for message, dict_ in zip(self._convert_input(input_).to_messages(), sent, strict=True):
            if isinstance(message, AIMessage) and message.tool_calls and reasoning_text(message):
                dict_[REQUEST_FIELD] = reasoning_text(message)
        return payload

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
        _keep(choices[0].get("delta") or {}, generation.message)
        return generation

    def _create_chat_result(
        self, response: dict | Any, generation_info: dict | None = None
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        body = response if isinstance(response, dict) else response.model_dump(warnings=False)
        for choice, generation in zip(body.get("choices") or [], result.generations, strict=False):
            if isinstance(generation.message, AIMessage):
                _keep(choice.get("message") or {}, generation.message)
        return result
