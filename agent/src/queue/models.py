"""The job payload on the queue and the events a job publishes, as JSON on both sides."""

from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

JobKind = Literal["chat", "research"]


class ClientInfo(BaseModel):
    """Who sent the request, from the headers the gateway forwards."""

    ip: str | None = None
    client: str | None = None


class JobRequest(BaseModel):
    """What a client asks for: a chat turn on a thread, or a research run on a ticker."""

    model_config = ConfigDict(extra="forbid")
    kind: JobKind
    thread_id: str = Field("main", pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    message: str | None = Field(None, min_length=1, max_length=20_000)
    ticker: str | None = Field(None, pattern=r"^[A-Za-z][A-Za-z0-9.-]{0,9}$")
    # POSTed the job's outcome once when it finishes.
    callback_url: HttpUrl | None = None

    @model_validator(mode="after")
    def _fields_match_kind(self) -> "JobRequest":
        if self.kind == "chat" and (self.message is None or self.ticker is not None):
            raise ValueError("a chat job needs a message and no ticker")
        if self.kind == "research" and (self.ticker is None or self.message is not None):
            raise ValueError("a research job needs a ticker and no message")
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


TERMINAL = frozenset({Done.type, Error.type})
