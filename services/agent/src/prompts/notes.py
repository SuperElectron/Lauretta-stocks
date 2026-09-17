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
# Put in place of an identifying value (IP address, place) in the model's streamed reasoning.
REDACTED = "[redacted]"
ERROR = "The desk could not answer: {message}."

SOUL_PROPOSAL = """---
Proposed change to my soul (id {short_id})
Reason: {reason}

Proposed text:

{content}

Reply `approve soul {short_id}` to apply it, or `reject soul {short_id}` to discard it."""

# The command line.
CLI_CHATTING = "chatting on thread {thread!r}; ctrl-d to quit"
CLI_TURN_FAILED = "[turn failed: {error}; see the log above]"
CLI_RESEARCHING = "researching {ticker}: Analyst, Auditor, Strategist (a minute or two)..."
CLI_SAVED = "saved to {path}"
CLI_REPLY = "\nassistant> {reply}\n"
CLI_THREAD_HELP = "conversation to continue"
