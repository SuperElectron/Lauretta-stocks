"""The progress labels a job reports while it works, shown to clients as reasoning.

The API turns each into a line with the agent's name and role (`contracts/job_events.v1.json`).
"""

ASSISTANT_WORKING = "working it"
# A model call that had only reasoned is tried again.
ASSISTANT_RETRYING = "retrying"
ANALYST_DRAFTING = "drafting the story"
ANALYST_REDRAFTING = "redrafting (revision {revision})"
CHECKER_CHECKING = "re-checking the numbers"
CHECKER_VERDICT = "verdict: {verdict}"
STRATEGIST_SIZING = "sizing it against your book"
SAVING = "saving the thesis"
# A long thread is summarised and its durable facts saved, after the reply.
COMPACTING = "filing the older notes"
