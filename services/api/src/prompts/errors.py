"""Error text a client reads from the API. `str.format` fields.

The chat notes wrap a job failure as `notes.ERROR`.
"""

# Why a job failed, as the client reads it after `ERROR`.
JOB_FAILED = "the job failed; the worker log has the details"
JOB_ABANDONED = "the job did not finish"
JOB_LOST = "its record expired before it finished; ask again"

# Startup.
DATABASE_UNAVAILABLE = "the database is unavailable; is `just up` running?"
NO_USER = "the run has no user to act for"

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
NOT_FROM_GATEWAY = "requests reach the api through the gateway only"

# Voice (`src/api/voice`).
SPEECH_UNAVAILABLE = "speech is not available right now; try again shortly"
AUDIO_TOO_LARGE = "the recording is too large; the limit is {limit} MB"
AUDIO_EMPTY = "no speech was heard in the recording"

# MCP tools (`src/api/mcpserver`): anything unexpected, without its details.
MCP_TOOL_FAILED = "the desk could not do that; the api log has the details"
