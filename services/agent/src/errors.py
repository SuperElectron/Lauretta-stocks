"""Typed agent errors. Each fails the run with a code; nothing is swallowed.

Each message is client-visible.
"""


class AgentError(Exception):
    code = "INTERNAL_ERROR"
    message = "the agent failed"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class DatabaseUnavailable(AgentError):
    code = "DATABASE_UNAVAILABLE"
    message = "the database is unavailable; is `just up` running?"


class EmbedderMismatch(AgentError):
    code = "EMBEDDER_MISMATCH"
    message = "the embedding model's size does not match EMBED_DIMS and the facts table"


class RoleDidNotSubmit(AgentError):
    """A research role stopped talking without handing in its work."""

    code = "ROLE_DID_NOT_SUBMIT"
    message = "a research role finished without submitting its result"


class ReplyTruncated(AgentError):
    """The model ran out of output tokens mid-reply; raise AGENT_MAX_TOKENS."""

    code = "REPLY_TRUNCATED"
    message = "the model hit AGENT_MAX_TOKENS mid-reply (reasoning counts too); raise it in .env"


class EmptyReply(AgentError):
    """The model reasoned, then stopped without an answer or a tool call."""

    code = "EMPTY_REPLY"
    message = "the model thought but gave no answer; send the message again"


class NoUser(AgentError):
    """A graph ran without the user it acts for; nothing is read or written."""

    code = "NO_USER"
    message = "the run has no user to act for"


class UpstreamUnavailable(Exception):
    """A data source could not be read. Says nothing about the company."""


class PersonaInvalid(AgentError):
    """A soul, identity, profile or signal value, or a soul decision, that cannot be stored as
    given."""

    code = "PERSONA_INVALID"
    message = "the persona is invalid"


class ThreadBusy(AgentError):
    """Another job held the conversation for longer than a job may wait for it."""

    code = "THREAD_BUSY"
    message = "another message on this thread is still being answered; send it again after"


class LockLost(AgentError):
    """The thread lock expired, or another job took it, while this job ran."""

    code = "LOCK_LOST"
    message = "the thread lock was lost while the job ran"


class JobInterrupted(AgentError):
    """A worker stopped mid-job. The job is not run again: its turn may already have written
    to the conversation, the database or the investor's screen."""

    code = "JOB_INTERRUPTED"
    message = "the job was interrupted before it finished; send it again if still needed"
