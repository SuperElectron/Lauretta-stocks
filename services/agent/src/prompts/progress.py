"""Every progress label a job reports while it works, shown to clients as reasoning.

A line reads `{title} {detail}…`. Stage keys are the graph's node names, not wording.
"""

TITLES = {
    "assistant": "Desk",
    "analyst": "Analyst",
    "checker": "Risk",
    "advisor": "PM",
    "save": "Desk",
}
LINE = "{title} {detail}…"

ASSISTANT_WORKING = "working it"
ANALYST_DRAFTING = "pulling the filings"
ANALYST_REDRAFTING = "redrafting (revision {revision})"
RISK_CHECKING = "re-checking the numbers"
RISK_VERDICT = "verdict: {verdict}"
PM_SIZING = "sizing it against your book"
SAVING = "saving the thesis"

# A tool step; the first letter is capitalised when the line is sent.
TOOL = {
    "started": "Consulting {name}…",
    "done": "{name} answered.",
    "error": "{name} failed.",
}
