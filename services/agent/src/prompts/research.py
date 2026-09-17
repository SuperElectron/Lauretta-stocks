"""The `<research>` block: what the desk started for the investor and how it is doing.

Rendered by `graph/research.py` from the job statuses, never written by the model.
"""

RUNNING = "{ticker}: the team is still on it; tell them if they ask, and do not start it again."
DONE = (
    "{ticker}: finished since your last reply. Read it with get_thesis and lead with the "
    "suggestion, then the why. Say once that it is a suggestion, not financial advice."
)
FAILED = "{ticker}: the run failed. Say so plainly and offer to put the team on it again."
