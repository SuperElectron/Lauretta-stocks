"""Runs one job: its thread lock, its events and status, its errors, and its callback.

A job's own failure ends in an `error` event with an `AgentError`'s code and message, or
`INTERNAL` for anything else, whose details go to the worker log only. A broker failure while
publishing is raised, so the consumer leaves the job pending for another delivery.
"""

from typing import Any

from loguru import logger
from redis.asyncio import Redis

from src.app import App
from src.errors import AgentError
from src.queue import events, submit
from src.queue.lock import ThreadLock
from src.queue.models import Done, Error, Event, Job, Reset
from src.settings import Settings
from src.worker import callback
from src.worker.stream import run_chat, run_research

INTERNAL = Error(code="INTERNAL", message="the job failed; the worker log has the details")


def error_event(exc: Exception) -> Error:
    if isinstance(exc, AgentError):
        return Error(code=exc.code, message=exc.message)
    return INTERNAL


class JobHandler:
    def __init__(self, app: App, broker: Redis, settings: Settings) -> None:
        self._app = app
        self._broker = broker
        self._settings = settings
        self._ttl_s = settings.EVENTS_TTL_S

    async def publish(self, job_id: str, event: Event) -> None:
        await events.publish(self._broker, job_id, event, self._ttl_s)

    async def run(self, job: Job) -> None:
        status = await submit.status_of(self._broker, job.job_id)
        if status is not None and status.get("status") in submit.FINISHED:
            logger.bind(job_id=job.job_id).warning("job.already_finished")
            return
        if await events.count(self._broker, job.job_id):
            # A redelivered job starts over; what the last attempt streamed is void.
            await self.publish(job.job_id, Reset())
        await submit.mark(
            self._broker, job.job_id, self._ttl_s, status="running", started_at=submit.now()
        )
        log = logger.bind(job_id=job.job_id, kind=job.kind)
        try:
            result = await self._execute(job)
        except Exception as exc:
            if isinstance(exc, AgentError):
                log.bind(code=exc.code).warning("job.failed")
            else:
                log.exception("job.failed")
            await self.finish(job, error_event(exc))
            return
        log.info("job.done")
        await self.finish(job, Done(result=result))

    async def dead(self, job: Job, reason: str) -> None:
        """The job was delivered too often without finishing; the reason stays in the log."""
        logger.bind(job_id=job.job_id, reason=reason).error("job.dead")
        await self.finish(job, Error(code="JOB_ABANDONED", message="the job did not finish"))

    async def finish(self, job: Job, outcome: Done | Error) -> None:
        await self.publish(job.job_id, outcome)
        fields = {"status": "done" if isinstance(outcome, Done) else "failed"}
        if isinstance(outcome, Error):
            fields["error_code"] = outcome.code
        await submit.mark(self._broker, job.job_id, self._ttl_s, **fields, finished_at=submit.now())
        if job.callback_url is None:
            return
        body: dict[str, Any] = {"job_id": job.job_id, **fields, outcome.type: outcome.model_dump()}
        reason = await callback.deliver(
            str(job.callback_url), body, self._settings.CALLBACK_TIMEOUT_S
        )
        if reason is not None:
            await submit.mark(self._broker, job.job_id, self._ttl_s, callback_error=reason)

    async def _execute(self, job: Job) -> dict[str, Any]:
        signals = {"ip": job.client.ip, "client": job.client.client, "channel": "api"}
        await self._app.record_signals(signals, "gateway")

        async def publish(event: Event) -> None:
            await self.publish(job.job_id, event)

        if job.kind == "research":
            return await run_research(self._app.pipeline, job.ticker, publish)
        lock = ThreadLock(
            self._broker,
            job.thread_id,
            self._settings.AGENT_LOCK_TTL_MS,
            self._settings.AGENT_LOCK_WAIT_MS,
        )
        async with lock.held():
            return await lock.guard(run_chat(self._app.chat, job.thread_id, job.message, publish))
