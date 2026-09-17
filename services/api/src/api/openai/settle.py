"""Recording a finished answer: its alias and the release of its request record.

It runs as its own task, started the moment the job's outcome is read, never inside the
response. Chat apps hang up as soon as they see `finish_reason` (openai-node aborts before
reading `[DONE]`), and Starlette then cancels the response body; a task outlives that. It never
holds up the closing chunk, though the response ends only once it is done. Its failure cannot
break an answer already sent: it is logged at error level, and costs only the alias, since the
next request falls back to its first-message thread and registers every pair it resends.
"""

import asyncio
from collections.abc import Awaitable, Callable

from loguru import logger

# Called with the answer text sent, and whether the job finished `done`.
Answered = Callable[[str, bool], Awaitable[None]]
# How long the response waits for the recording: a stalled database must not hold a finished
# answer open. The task carries on past it and still logs its own failure.
FINISH_TIMEOUT_S = 10.0
# Strong references: the event loop keeps only weak ones to running tasks.
running: set[asyncio.Task[None]] = set()


def _finished(job_id: str, task: asyncio.Task[None]) -> None:
    running.discard(task)
    if task.cancelled():
        logger.bind(job_id=job_id).error("openai.answer_not_recorded")
    elif (exc := task.exception()) is not None:
        logger.bind(job_id=job_id).opt(exception=exc).error("openai.answer_not_recorded")


def start(job_id: str, answered: Answered, text: str, done: bool) -> asyncio.Task[None]:
    """Records the answer `text` in a task of its own; `done` when the job finished `done`."""
    task = asyncio.create_task(answered(text, done), name=job_id)
    running.add(task)
    task.add_done_callback(lambda finished: _finished(job_id, finished))
    return task


async def finish(tasks: list[asyncio.Task[None]], timeout: float = FINISH_TIMEOUT_S) -> None:
    """Waits for the recording before the response ends, so a client that reads to the end
    and asks again at once finds the alias. Being cancelled here (the client hung up) leaves
    the tasks running; their failures are already logged. It waits at most `timeout` seconds,
    then ends the response anyway and logs the jobs still recording."""
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        logger.bind(job_id=task.get_name()).error("openai.answer_recording_slow")
