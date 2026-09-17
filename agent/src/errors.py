"""Typed agent errors. Each fails the run with a code; nothing is swallowed."""


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


class UpstreamUnavailable(Exception):
    """A data source could not be read. Says nothing about the company."""


class PersonaInvalid(AgentError):
    """A soul, identity or user file or proposal that cannot be stored as given."""

    code = "PERSONA_INVALID"
    message = "the persona is invalid"
