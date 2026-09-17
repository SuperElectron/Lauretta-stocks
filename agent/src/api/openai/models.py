"""What an OpenAI Chat Completions client sends, and the errors it understands.

Clients send more than the court uses (temperature, max_tokens, their own system prompt and
history); extra fields are accepted and ignored.
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# The Director: the only model this API serves.
MODEL = "lauretta"


class OpenAIError(Exception):
    """Answered as OpenAI's error body; `message` is written for the person using the client."""

    def __init__(
        self,
        status: int,
        message: str,
        code: str,
        *,
        kind: str = "invalid_request_error",
        param: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.kind = kind
        self.param = param

    def body(self) -> dict[str, Any]:
        return {
            "error": {
                "message": self.message,
                "type": self.kind,
                "param": self.param,
                "code": self.code,
            }
        }


async def error_response(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, OpenAIError)
    return JSONResponse(exc.body(), status_code=exc.status)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    # Plain text, or a list of parts of which only the `text` ones are read.
    content: str | list[dict[str, Any]] | None = None

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        parts = self.content or []
        texts = (p.get("text") for p in parts if p.get("type") == "text")
        return "".join(text for text in texts if isinstance(text, str))


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(max_length=100)
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False

    def last_user_text(self) -> str:
        """The message this turn answers. Tool results are not taken yet."""
        last = self.messages[-1]
        if last.role != "user" or not last.text().strip():
            raise OpenAIError(
                400,
                "the last message must be the user's, with text",
                "invalid_last_message",
                param="messages",
            )
        return last.text()

    def user_texts(self) -> list[str]:
        return [m.text() for m in self.messages if m.role == "user"]


async def chat_request(request: Request) -> ChatRequest:
    """The request body, or a 400 naming the fields at fault (never echoing their values)."""
    try:
        body = await request.json()
        parsed = ChatRequest.model_validate(body)
    except ValueError as exc:
        if not isinstance(exc, ValidationError):
            raise OpenAIError(400, "the body is not valid JSON", "invalid_json") from exc
        fields = ", ".join(".".join(str(p) for p in e["loc"]) or "body" for e in exc.errors())
        raise OpenAIError(400, f"invalid request fields: {fields}", "invalid_request") from exc
    if parsed.model_extra:
        logger.bind(fields=sorted(parsed.model_extra)).debug("openai.fields_ignored")
    return parsed
