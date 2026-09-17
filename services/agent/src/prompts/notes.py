"""What the investor reads besides the assistant's own reply. `str.format` fields.

The API's own chat notes live in `services/api/src/prompts/notes.py`.
"""

# Put in place of an identifying value (IP address, place) in the model's streamed reasoning.
REDACTED = "[redacted]"

SOUL_PROPOSAL = """---
Proposed change to my soul (id {short_id})
Reason: {reason}

Proposed text:

{content}

Reply `approve soul {short_id}` to apply it, or `reject soul {short_id}` to discard it."""

# Under the reply to a message that approved or rejected a proposal, keyed by outcome
# (`persona/approval.py`); any other outcome uses "other". Fields: verb, short_id, outcome,
# reason, days.
SOUL_DECISION = {
    "approved": "---\nSoul change {short_id} applied: {reason}.",
    "rejected": "---\nSoul change {short_id} rejected: {reason}. The soul is unchanged.",
    "unknown": "---\nNo soul proposal {short_id} was found; nothing changed.",
    "ambiguous": "---\n{short_id} matches more than one soul proposal; nothing changed. Reply "
    "with more of the id.",
    "expired": "---\nSoul proposal {short_id} is older than {days} days and expired; nothing "
    "changed.",
    "stale": "---\nSoul proposal {short_id} was written against an older soul, so it was not "
    "applied; nothing changed. Ask for it to be proposed again.",
    "other": "---\nCould not {verb} soul proposal {short_id} ({outcome}); nothing changed.",
}

# The command line.
CLI_CHATTING = "chatting on thread {thread!r}; ctrl-d to quit"
CLI_TURN_FAILED = "[turn failed: {error}; see the log above]"
CLI_RESEARCHING = "researching {ticker}: Analyst, Checker, Strategist (a minute or two)..."
CLI_SAVED = "saved to {path}"
CLI_REPLY = "\nassistant> {reply}\n"
CLI_THREAD_HELP = "conversation to continue"
CLI_USER_HELP = "the user to act for (default: the owner, first in ALLOWED_USERS)"
CLI_UNKNOWN_USER = "{user!r} is not in ALLOWED_USERS"
