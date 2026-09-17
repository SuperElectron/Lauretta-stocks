"""Research runs the Director started and has not reported yet.

A run takes minutes, so the chat turn never waits for one: `start` hands the ticker over and
returns, `active` says how each started run is doing, and `clear` forgets the ones already
reported. The worker keeps them on the broker as ordinary research jobs, so a restart loses
nothing; the CLI keeps them in its own process.
"""

import asyncio
from typing import Any, Protocol

from redis.asyncio import Redis

from src.graph.ctx import Ctx
from src.queue import keys, submit
from src.queue.models import ClientInfo, Job
from src.tools.research import RunResearch

# The app that queued it, on a job the desk started for itself.
DESK = ClientInfo(client="desk")


class Runs(Protocol):
    """Whether a run was started here or queued for a worker, a caller sees the same three."""

    async def start(self, user: str, ticker: str) -> dict[str, str]:
        """Starts research on `ticker` for `user`, or returns the run already going on it.

        `{"ticker": ..., "job_id": ..., "status": "queued" | "running"}`.
        """

    async def active(self, user: str) -> list[dict[str, str]]:
        """Every run started for `user` and not yet cleared, each with its current status."""

    async def clear(self, user: str, job_ids: list[str]) -> None:
        """Forgets runs already reported to the investor."""


def started(ticker: str, job_id: str, status: str) -> dict[str, str]:
    return {"ticker": ticker, "job_id": job_id, "status": status}


class QueuedRuns:
    """Runs as jobs on the queue, the same ones the API submits, so any worker may pick one up.

    `research:{user}` (a hash of job id to ticker) is what the desk has started and not yet
    reported; each job's own status hash says how it is doing.
    """

    def __init__(self, broker: Redis, ttl_s: int) -> None:
        self._broker = broker
        self._ttl_s = ttl_s

    async def start(self, user: str, ticker: str) -> dict[str, str]:
        for run in await self.active(user):
            if run["ticker"] == ticker and run["status"] in (keys.QUEUED, keys.RUNNING):
                return run
        job = Job(kind="research", ticker=ticker, user=user, client=DESK)
        await submit.enqueue(self._broker, job, self._ttl_s)
        await self._broker.hset(keys.runs(user), job.job_id, ticker)
        await self._broker.expire(keys.runs(user), self._ttl_s)
        return started(ticker, job.job_id, keys.QUEUED)

    async def active(self, user: str) -> list[dict[str, str]]:
        found = await self._broker.hgetall(keys.runs(user))
        runs = []
        for job_id, ticker in found.items():
            status = await submit.status_of(self._broker, job_id)
            # A job whose record expired before the investor came back: the thesis is saved.
            runs.append(started(ticker, job_id, (status or {}).get(keys.STATUS, keys.DONE)))
        return runs

    async def clear(self, user: str, job_ids: list[str]) -> None:
        if job_ids:
            await self._broker.hdel(keys.runs(user), *job_ids)


class LocalRuns:
    """Runs in this process, for the CLI: the pipeline as a background task, kept in memory."""

    def __init__(self, research: RunResearch) -> None:
        self._research = research
        self._tasks: dict[str, tuple[str, str, asyncio.Task[Any]]] = {}

    async def start(self, user: str, ticker: str) -> dict[str, str]:
        for run in await self.active(user):
            if run["ticker"] == ticker and run["status"] in (keys.QUEUED, keys.RUNNING):
                return run
        task = asyncio.create_task(self._research(ticker, Ctx(user_id=user)))
        job_id = f"local-{len(self._tasks) + 1}"
        self._tasks[job_id] = (user, ticker, task)
        return started(ticker, job_id, keys.RUNNING)

    async def active(self, user: str) -> list[dict[str, str]]:
        runs = []
        for job_id, (owner, ticker, task) in self._tasks.items():
            if owner != user:
                continue
            status = keys.RUNNING
            if task.done():
                status = keys.FAILED if task.exception() else keys.DONE
            runs.append(started(ticker, job_id, status))
        return runs

    async def clear(self, _user: str, job_ids: list[str]) -> None:
        for job_id in job_ids:
            self._tasks.pop(job_id, None)
