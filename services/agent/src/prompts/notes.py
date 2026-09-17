"""What the investor reads besides the assistant's own reply. `str.format` fields.

`TIMED_OUT` and `WAITING` are fixed notes: `api/openai/threads.py` never aliases a thread by them.
"""

STILL_WORKING = "Still working the trade. Give it a minute, then ask for the result."
TIMED_OUT = f"_({STILL_WORKING})_"
WAITING = (
    "Waiting on the desk to finish your last request; if it is still busy after half a minute, "
    "send again once it has answered.\n"
)
RETRYING = "\n\n_(retrying…)_\n\n"
ERROR = "The desk could not answer: {message}."

# Why a job failed, as the client reads it after `ERROR`.
JOB_FAILED = "the job failed; the worker log has the details"
JOB_ABANDONED = "the job did not finish"
JOB_LOST = "its record expired before it finished; ask again"

# Each `AgentError`'s message, shown after `ERROR`.
AGENT_FAILED = "the agent failed"
DATABASE_UNAVAILABLE = "the database is unavailable; is `just up` running?"
EMBEDDER_MISMATCH = "the embedding model's size does not match EMBED_DIMS and the facts table"
ROLE_DID_NOT_SUBMIT = "a research role finished without submitting its result"
REPLY_TRUNCATED = (
    "the model hit AGENT_MAX_TOKENS mid-reply (reasoning counts too); raise it in .env"
)
PERSONA_INVALID = "the persona is invalid"
THREAD_BUSY = "another message on this thread is still being answered; send it again after"
LOCK_LOST = "the thread lock was lost while the job ran"
JOB_INTERRUPTED = "the job was interrupted before it finished; send it again if still needed"
ROLE_STOPPED = "the {role} stopped without submitting its work"
SOUL_EMPTY = "the soul is empty"
SOUL_TOO_LONG = "the soul is {chars} chars; the cap is {cap}"

SOUL_PROPOSAL = """---
Proposed change to my soul (id {short_id})
Reason: {reason}

Proposed text:

{content}

Reply `approve soul {short_id}` to apply it, or `reject soul {short_id}` to discard it."""

# The command line.
CLI_CHATTING = "chatting on thread {thread!r}; ctrl-d to quit"
CLI_TURN_FAILED = "[turn failed: {error}; see the log above]"
CLI_RESEARCHING = "researching {ticker}: Analyst, Risk, PM (a minute or two)..."
CLI_SAVED = "saved to {path}"
