"""Messages the code sends the model mid-run, beside the system prompt. `str.format` fields."""

# Sent to a research role that replied without calling a tool (`graph/role.py`), before it fails.
SUBMIT_REMINDER = (
    "You answered without calling a tool, so nothing was handed in. Your work counts only once "
    "you call {submit}. Call {submit} now with your result."
)
