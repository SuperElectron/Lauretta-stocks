"""The job payload on the queue and the events a job publishes, as JSON on both sides.

Events, in the order a client may see them: `progress`, `tool`, `token`, `message_end` (text
before a tool call is complete), `reset` (discard the partial message), `notice`, and last
`done` or `error`. The API alone sends `timeout` when a stream reaches its cap; it is never
stored, and the job carries on.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.prompts import errors as wording

JobKind = Literal["chat", "research"]


class ClientInfo(BaseModel):
    """Which app sent the request, from the headers the gateway forwards; `unknown` when it
    does not name itself plainly."""

    client: str = "unknown"


class JobRequest(BaseModel):
    """What a client asks for: a chat turn on a thread, or a research run on a ticker."""

    model_config = ConfigDict(extra="forbid")
    kind: JobKind
    thread_id: str = Field("main", pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    message: str | None = Field(None, min_length=1, max_length=20_000)
    ticker: str | None = Field(None, pattern=r"^[A-Za-z][A-Za-z0-9.-]{0,9}$")

    @model_validator(mode="after")
    def _fields_match_kind(self) -> "JobRequest":
        if self.kind == "chat" and (self.message is None or self.ticker is not None):
            raise ValueError(wording.CHAT_JOB_FIELDS)
        if self.kind == "research" and (self.ticker is None or self.message is not None):
            raise ValueError(wording.RESEARCH_JOB_FIELDS)
        return self


class Job(JobRequest):
    """A request as queued: with its id and who sent it."""

    job_id: str = Field(default_factory=lambda: uuid4().hex)
    client: ClientInfo = ClientInfo()
    submitted_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Event(BaseModel):
    """One event on `job:{id}:events`; `type` is the SSE event name, the fields its data."""

    type: ClassVar[str]


class Token(Event):
    type = "token"
    text: str


class Progress(Event):
    type = "progress"
    stage: str
    detail: str


class Tool(Event):
    type = "tool"
    name: str
    status: Literal["started", "done", "error"]


class MessageEnd(Event):
    """The assistant's text so far is a finished message: it now calls a tool, and any later
    tokens start a new message."""

    type = "message_end"


class Reset(Event):
    """A model call was retried after its tokens were sent: discard the partial message."""

    type = "reset"


class Notice(Event):
    type = "notice"
    text: str


class Done(Event):
    type = "done"
    result: dict[str, Any]


class Error(Event):
    """Only an `AgentError`'s code and message, or `INTERNAL`; never a trace or payload."""

    type = "error"
    code: str
    message: str


class Timeout(Event):
    """Sent by the API, not the worker: this stream hit `API_MAX_STREAM_S`, the job goes on."""

    type = "timeout"
    code: str
    message: str


TERMINAL = frozenset({Done.type, Error.type})
