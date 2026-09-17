"""Typed agent errors. Each fails the run with a code; nothing is swallowed.

The messages are client-visible wording and live in `prompts/errors.py`.
"""

from src.prompts import errors as wording


class AgentError(Exception):
    code = "INTERNAL_ERROR"
    message = wording.AGENT_FAILED

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class DatabaseUnavailable(AgentError):
    code = "DATABASE_UNAVAILABLE"
    message = wording.DATABASE_UNAVAILABLE


class EmbedderMismatch(AgentError):
    code = "EMBEDDER_MISMATCH"
    message = wording.EMBEDDER_MISMATCH


class RoleDidNotSubmit(AgentError):
    """A research role stopped talking without handing in its work."""

    code = "ROLE_DID_NOT_SUBMIT"
    message = wording.ROLE_DID_NOT_SUBMIT


class ReplyTruncated(AgentError):
    """The model ran out of output tokens mid-reply; raise AGENT_MAX_TOKENS."""

    code = "REPLY_TRUNCATED"
    message = wording.REPLY_TRUNCATED


class EmptyReply(AgentError):
    """The model reasoned, then stopped without an answer or a tool call."""

    code = "EMPTY_REPLY"
    message = wording.EMPTY_REPLY


class NoUser(AgentError):
    """A graph ran without the user it acts for; nothing is read or written."""

    code = "NO_USER"
    message = wording.NO_USER


class UpstreamUnavailable(Exception):
    """A data source could not be read. Says nothing about the company."""


class PersonaInvalid(AgentError):
    """A soul, identity, profile or signal value, or a soul decision, that cannot be stored as
    given."""

    code = "PERSONA_INVALID"
    message = wording.PERSONA_INVALID


class ThreadBusy(AgentError):
    """Another job held the conversation for longer than a job may wait for it."""

    code = "THREAD_BUSY"
    message = wording.THREAD_BUSY


class LockLost(AgentError):
    """The thread lock expired, or another job took it, while this job ran."""

    code = "LOCK_LOST"
    message = wording.LOCK_LOST


class JobInterrupted(AgentError):
    """A worker stopped mid-job. The job is not run again: its turn may already have written
    to the conversation, the database or the investor's screen."""

    code = "JOB_INTERRUPTED"
    message = wording.JOB_INTERRUPTED
