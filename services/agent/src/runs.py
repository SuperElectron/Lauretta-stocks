"""Research runs the Director started and has not reported yet.

A run takes minutes: `start` hands the ticker over, `follow` watches it for as long as the
investor is worth keeping waiting (relaying the team's progress so they see it working), `active`
says how each started run is doing and `clear` forgets the ones already reported. The run itself
belongs to no turn: the worker keeps it on the broker as an ordinary research job, so letting go
of it, a dropped client or a restart lose nothing, and whatever is not reported in the turn that
started it is reported in a later one. The CLI keeps its runs in its own process.

One run per ticker per investor: the ticker is the key, claimed before the job is queued, so two
turns at once cannot put the team on the same company twice.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from itertools import count
from typing import Any, Protocol

from redis.asyncio import Redis

from src.graph.ctx import Ctx
from src.queue import events, keys, submit
from src.queue.models import DESK, ClientInfo, Job
from src.tools.research import RunResearch

# A run we can no longer ask about: its job record expired or it never reached a worker. Never a
# job status (`keys.STATUSES`); the investor is told it was lost, never that it finished.
LOST = "lost"
GOING = (keys.QUEUED, keys.RUNNING)

# Called with each progress event of the run being followed: its stage, detail and agent name.
OnProgress = Callable[[str, str, str | None], Awaitable[None] | None]


class Runs(Protocol):
    """Whether a run was started here or queued for a worker, a caller sees the same three."""

    async def start(self, user: str, ticker: str) -> dict[str, str]:
        """Starts research on `ticker` for `user`, or returns the run already going on it.

        `{"ticker": ..., "job_id": ..., "status": "queued" | "running"}`.
        """

    async def follow(
        self, user: str, ticker: str, seconds: float, on_progress: OnProgress
    ) -> dict[str, Any] | None:
        """The run's result once it finishes, or None when `seconds` pass with it still going.

        A finished or failed run is reported here, so it is forgotten; one still going stays for
        a later turn to report.
        """

    async def active(self, user: str) -> list[dict[str, str]]:
        """Every run started for `user` and not yet cleared, each with its current status."""

    async def clear(self, user: str, tickers: list[str]) -> None:
        """Forgets runs already reported to the investor."""


def started(ticker: str, job_id: str, status: str) -> dict[str, str]:
    return {"ticker": ticker, "job_id": job_id, "status": status}


class QueuedRuns:
    """Runs as jobs on the queue, the same ones the API submits, so any worker may pick one up.

    `research:{user}` (a hash of ticker to job id) is what the desk has started and not yet
    reported; each job's own status hash says how it is doing. The ticker's field is claimed
    first and given up again if queueing fails, so a tracked run is always a queued one.
    """

    def __init__(self, broker: Redis, ttl_s: int) -> None:
        self._broker = broker
        self._ttl_s = ttl_s

    async def start(self, user: str, ticker: str) -> dict[str, str]:
        job = Job(kind="research", ticker=ticker, user=user, client=ClientInfo(client=DESK))
        claimed = await self._broker.hsetnx(keys.runs(user), ticker, job.job_id)
        if not claimed:
            going = await self._going(user, ticker)
            if going is not None:
                return going
            # The tracked run is finished or lost: this one takes its place.
            await self._broker.hset(keys.runs(user), ticker, job.job_id)
        try:
            await submit.enqueue(self._broker, job, self._ttl_s)
        except Exception:
            await self._broker.hdel(keys.runs(user), ticker)
            raise
        await self._broker.expire(keys.runs(user), self._ttl_s)
        return started(ticker, job.job_id, keys.QUEUED)

    async def follow(
        self, user: str, ticker: str, seconds: float, on_progress: OnProgress
    ) -> dict[str, Any] | None:
        job_id = await self._broker.hget(keys.runs(user), ticker)
        if job_id is None:
            return None
        deadline = asyncio.get_running_loop().time() + seconds
        async for event in events.follow(self._broker, job_id, deadline):
            data = json.loads(event.data)
            if event.type == "progress":
                await _relayed(on_progress, data)
            elif event.type in ("done", "error"):
                await self.clear(user, [ticker])
                return data.get("result", data) if event.type == "done" else {"error": data}
        return None

    async def active(self, user: str) -> list[dict[str, str]]:
        found = await self._broker.hgetall(keys.runs(user))
        return [
            started(ticker, job_id, await self._status(job_id)) for ticker, job_id in found.items()
        ]

    async def clear(self, user: str, tickers: list[str]) -> None:
        if tickers:
            await self._broker.hdel(keys.runs(user), *tickers)

    async def _status(self, job_id: str) -> str:
        """The job's status, or `LOST` once its record is gone: it may have finished before the
        record expired, or never have run at all, and the desk never guesses which."""
        found = await submit.status_of(self._broker, job_id)
        return (found or {}).get(keys.STATUS, LOST)

    async def _going(self, user: str, ticker: str) -> dict[str, str] | None:
        """The run already on this ticker, while it is still queued or running."""
        job_id = await self._broker.hget(keys.runs(user), ticker)
        if job_id is None:
            return None
        status = await self._status(job_id)
        return started(ticker, job_id, status) if status in GOING else None


async def _relayed(on_progress: OnProgress, data: dict[str, Any]) -> None:
    sent = on_progress(data["stage"], data["detail"], data.get("name"))
    if sent is not None:
        await sent


class LocalRuns:
    """Runs in this process, for the CLI: the pipeline as a background task, kept in memory."""

    def __init__(self, research: RunResearch) -> None:
        self._research = research
        self._ids = count(1)
        self._tasks: dict[tuple[str, str], tuple[str, asyncio.Task[Any]]] = {}

    async def start(self, user: str, ticker: str) -> dict[str, str]:
        going = self._tasks.get((user, ticker))
        if going is not None and not going[1].done():
            return started(ticker, going[0], keys.RUNNING)
        task = asyncio.create_task(self._research(ticker, Ctx(user_id=user)))
        job_id = f"local-{next(self._ids)}"
        self._tasks[(user, ticker)] = (job_id, task)
        return started(ticker, job_id, keys.RUNNING)

    async def follow(
        self, user: str, ticker: str, seconds: float, _on_progress: OnProgress
    ) -> dict[str, Any] | None:
        """The CLI's own run: its progress is the graph's, already on this process's stream."""
        going = self._tasks.get((user, ticker))
        if going is None:
            return None
        try:
            result = await asyncio.wait_for(asyncio.shield(going[1]), seconds)
        except TimeoutError:
            return None
        except Exception as exc:  # noqa: BLE001
            await self.clear(user, [ticker])
            return {"error": {"code": type(exc).__name__}}
        await self.clear(user, [ticker])
        return result

    async def active(self, user: str) -> list[dict[str, str]]:
        runs = []
        for (owner, ticker), (job_id, task) in self._tasks.items():
            if owner != user:
                continue
            status = keys.RUNNING
            if task.done():
                status = keys.FAILED if task.exception() else keys.DONE
            runs.append(started(ticker, job_id, status))
        return runs

    async def clear(self, user: str, tickers: list[str]) -> None:
        for ticker in tickers:
            self._tasks.pop((user, ticker), None)

    async def drain(self) -> None:
        """Waits for every run still going, so leaving does not abandon one mid-flight."""
        tasks = [task for _job_id, task in self._tasks.values() if not task.done()]
        await asyncio.gather(*tasks, return_exceptions=True)
