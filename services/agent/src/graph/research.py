"""What the desk is researching, as the `<research>` block of the assistant's prompt.

A run started in an earlier turn goes on in the background (`src/runs.py`). Every investor
message asks how each one is doing: the ones still going are named so the desk does not start
them twice, and a finished one is reported once and then forgotten. Forgetting it loses nothing:
its thesis is saved and listed in `<theses>`.
"""

from src.prompts import research as wording
from src.queue import keys
from src.runs import Runs

LINES = {keys.QUEUED: wording.RUNNING, keys.RUNNING: wording.RUNNING, keys.FAILED: wording.FAILED}


async def research_block(runs: Runs, user: str) -> str:
    """The block for this turn, empty when the desk has nothing to report, and the finished and
    failed runs in it are cleared: they are reported in this turn and not again."""
    active = await runs.active(user)
    if not active:
        return ""
    lines = [LINES.get(run["status"], wording.DONE).format(ticker=run["ticker"]) for run in active]
    reported = [run["job_id"] for run in active if run["status"] not in (keys.QUEUED, keys.RUNNING)]
    await runs.clear(user, reported)
    return "<research>\n" + "\n".join(lines) + "\n</research>"
