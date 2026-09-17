"""What the MCP tools do, for one user: queue jobs, follow their events, read saved results.

The same jobs, queue and reads as the HTTP API; the MCP layer (`server.py`) only names the user
and turns progress events into MCP progress notifications.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

from src.db.queries import holdings, theses, threads
from src.prompts import errors as wording
from src.queue import events, keys, submit
from src.queue.models import ClientInfo, Job
from src.settings import Settings

# Called with each progress line while a job runs.
OnProgress = Callable[[str], Awaitable[None]]
CLIENT = ClientInfo(client="mcp")


class DeskError(Exception):
    """A failure the MCP client sees as a tool error, with wording from `src.prompts`."""


@dataclass(frozen=True)
class Desk:
    broker: Redis
    pool: AsyncConnectionPool
    settings: Settings
    user: str

    async def start(self, **request: Any) -> str:
        """Queues a job for this user and returns its id."""
        job = Job(**request, user=self.user, client=CLIENT)
        if job.kind == "chat":
            await threads.create(self.pool, self.user, job.thread_id, CLIENT.client)
        await submit.submit(self.broker, job, self.settings.EVENTS_TTL_S)
        return job.job_id

    async def follow(self, job_id: str, on_progress: OnProgress) -> dict[str, Any]:
        """The job's result once it is done, reporting each progress line on the way."""
        async for event in events.read(self.broker, job_id):
            data = json.loads(event.data)
            if event.type == "progress":
                name = data.get("name")
                await on_progress(f"{name}: {data['detail']}" if name else data["detail"])
            elif event.type == "done":
                return data["result"]
            elif event.type == "error":
                raise DeskError(data["message"])
        raise DeskError(wording.JOB_ABANDONED)

    async def job(self, job_id: str) -> dict[str, Any]:
        """The job's status, and its result or error once finished; only this user's jobs."""
        status = await submit.status_of(self.broker, job_id)
        if status is None or status.get(keys.USER) != self.user:
            raise DeskError(wording.NO_SUCH_JOB)
        found: dict[str, Any] = {"job_id": job_id, "status": status.get(keys.STATUS)}
        last = await events.last_terminal(self.broker, job_id)
        if last is not None:
            data = json.loads(last.data)
            found["result" if last.type == "done" else "error"] = (
                data["result"] if last.type == "done" else data["message"]
            )
        return found

    async def thesis(self, ticker: str) -> dict[str, Any]:
        saved = await theses.latest(self.pool, self.user, ticker)
        if saved is None:
            raise DeskError(wording.NO_RESEARCH.format(ticker=ticker))
        return saved

    async def holdings(self) -> list[dict[str, Any]]:
        return await holdings.all_of(self.pool, self.user)
