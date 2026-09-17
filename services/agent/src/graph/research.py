"""What the desk is researching, as the `<research>` block of the assistant's prompt.

A run started in an earlier turn goes on in the background (`src/runs.py`). Every investor
message asks how each one is doing: the ones still going are named so the desk does not start
them twice, and a finished one is reported once and then forgotten. Forgetting it loses nothing:
its thesis is saved and listed in `<theses>`.
"""

from src.prompts import research as wording
from src.queue import keys
from src.runs import GOING, LOST, Runs

LINES = {
    keys.QUEUED: wording.RUNNING,
    keys.RUNNING: wording.RUNNING,
    keys.FAILED: wording.FAILED,
    keys.DONE: wording.DONE,
    LOST: wording.LOST,
}


async def research_block(runs: Runs, user: str, reported: list[str]) -> tuple[str, list[str]]:
    """The block for this turn, and the tickers it reports as over.

    `reported` is what the previous message's block already said was over: forgotten now, so a
    finished run is reported once, and a turn that died before its reply reports it again.
    """
    await runs.clear(user, reported)
    active = await runs.active(user)
    if not active:
        return "", []
    lines = [LINES[run["status"]].format(ticker=run["ticker"]) for run in active]
    over = [run["ticker"] for run in active if run["status"] not in GOING]
    return "<research>\n" + "\n".join(lines) + "\n</research>", over
