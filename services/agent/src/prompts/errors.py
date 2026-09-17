"""Error text a client, the model or an operator reads: job failures, `AgentError` messages,
API validation and dead letters. `str.format` fields.

The chat notes wrap a job failure as `notes.ERROR`.
"""

# Why a job failed, as the client reads it after `ERROR`.
JOB_FAILED = "the job failed; the worker log has the details"
JOB_ABANDONED = "the job did not finish"
JOB_LOST = "its record expired before it finished; ask again"

# Each `AgentError`'s message, shown after `ERROR`.
AGENT_FAILED = "the agent failed"
DATABASE_UNAVAILABLE = "the database is unavailable; is `just up` running?"
CHECKPOINTS_NOT_MIGRATED = (
    "the checkpoint tables are missing or out of date; run `docker compose run --rm migrate`"
)
EMBEDDER_MISMATCH = "the embedding model's size does not match EMBED_DIMS and the facts table"
ROLE_DID_NOT_SUBMIT = "a research role finished without submitting its result"
REPLY_TRUNCATED = (
    "the model hit AGENT_MAX_TOKENS mid-reply (reasoning counts too); raise it in .env"
)
EMPTY_REPLY = "the model thought but gave no answer; send the message again"
PERSONA_INVALID = "the persona is invalid"
THREAD_BUSY = "another message on this thread is still being answered; send it again after"
LOCK_LOST = "the thread lock was lost while the job ran"
JOB_INTERRUPTED = "the job was interrupted before it finished; send it again if still needed"
ROLE_STOPPED = "the {role} stopped without submitting its work"
NO_USER = "the run has no user to act for"
SOUL_EMPTY = "the soul is empty"
SOUL_TOO_LONG = "the soul is {chars} chars; the cap is {cap}"

# API errors (`HTTPException` details and OpenAI-style errors).
NO_SUCH_JOB = "no such job"
UNKNOWN_USER = "this request names no user of the desk"
NOT_AN_EVENT_ID = "not an event id"
STREAM_TIMEOUT = "this stream reached its time limit; the job carries on, reconnect to follow it"
NO_RESEARCH = "no research on {ticker}"
NO_SUCH_MODEL = "no such model; use {model!r}"
BAD_THREAD_HEADER = "X-Thread-Id must be 1-64 letters, digits or _.:-"
MESSAGE_TOO_LONG = "the last message is too long"
LAST_MESSAGE_NOT_USER = "the last message must be the user's, with text"
FIRST_MESSAGE_EMPTY = "the first user message must have text"
BODY_NOT_JSON = "the body is not valid JSON"
INVALID_FIELDS = "invalid request fields: {fields}"
CHAT_JOB_FIELDS = "a chat job needs a message and no ticker"
RESEARCH_JOB_FIELDS = "a research job needs a ticker and no message"

# Persona writes the code refuses.
NOT_KEYS_OF_KIND = "not {kind} keys: {keys}"
SIGNAL_SOURCE = "signals come from {sources}, not {source}"
PROPOSAL_NOT_PROPOSED = "soul proposal {proposal_id} is no longer proposed"

# Startup and data sources.
EMBEDDER_DIMS = "{model} returns {dims}-dim vectors but EMBED_DIMS={expected}"
EMBEDDER_NOT_STARTED = "Embedder.start() was not awaited"
YAHOO_FAILED = "Yahoo Finance failed: {error}"
SEC_UNREACHABLE = "SEC EDGAR unreachable: {error}"
SEC_STATUS = "SEC EDGAR returned {status}"

# Why a delivery was dead-lettered (the dead-letter stream and the worker log).
DEAD_INVALID_PAYLOAD = "invalid payload"
DEAD_UNFINISHED = "not finished in {deliveries} deliveries"

# Voice (`src/api/voice`).
SPEECH_UNAVAILABLE = "speech is not available right now; try again shortly"
AUDIO_TOO_LARGE = "the recording is too large; the limit is {limit} MB"
AUDIO_EMPTY = "no speech was heard in the recording"
