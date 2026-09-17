"""Every progress label a job reports while it works, shown to clients as reasoning.

A line reads `{name} ({role}) {detail}…` for a research role and `{name} {detail}…` for the
Director; the name is the agent's current one. Stage keys are the graph's node names.
"""

# The role each research stage's agent plays; the Director's own stages have no role shown.
ROLES = {
    "analyst": "Analyst",
    "checker": "Auditor",
    "advisor": "Strategist",
}
LINE = "{name} {detail}…"
ROLE_LINE = "{name} ({role}) {detail}…"

ASSISTANT_WORKING = "working it"
# A model call that had only reasoned is tried again.
ASSISTANT_RETRYING = "retrying"
ANALYST_DRAFTING = "drafting the story"
ANALYST_REDRAFTING = "redrafting (revision {revision})"
AUDITOR_CHECKING = "re-checking the numbers"
AUDITOR_VERDICT = "verdict: {verdict}"
STRATEGIST_SIZING = "sizing it against your book"
SAVING = "saving the thesis"

# A tool step; the first letter is capitalised when the line is sent.
TOOL = {
    "started": "Consulting {name}…",
    "done": "{name} answered.",
    "error": "{name} failed.",
}
