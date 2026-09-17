"""Runs one job, for the user it carries: its thread lock, its events and its status.

- A job's own failure ends in an `error` event with an `AgentError`'s code and message, or
  `INTERNAL` for anything else, whose details go to the worker log only. Either way the job is
  finished and acked.
- A broker failure while publishing the outcome or marking the status is raised, so the
  consumer leaves the job pending for another delivery. One inside the run itself (a token or
  progress event, the thread lock) is caught like any failure of the job and ends as
  `INTERNAL`; if that outcome cannot be published either, it is raised as above, and the
  redelivered job fails `JOB_INTERRUPTED`.
- A job delivered again is never run again once it started. If it already published `done` or
  `error`, only its status is brought up to date; otherwise it fails `JOB_INTERRUPTED`.
- Edge case: if the broker is unreachable for longer than `BROKER_MIN_IDLE_MS` while worker A
  runs a job, worker B may reclaim it and publish `JOB_INTERRUPTED`, and A may later publish
  `done` too. Readers stop at the first terminal event, so they see `JOB_INTERRUPTED`, while
  the status ends as whichever outcome was marked last. Not guarded against: it needs a long
  broker outage, and the turn A finished is still in the thread.
"""

import json
from typing import Any

from loguru import logger
from redis.asyncio import Redis

from src.app import App
from src.errors import AgentError, JobInterrupted
from src.queue import events, keys, submit
from src.queue.lock import ThreadLock
from src.queue.models import Done, Error, Event, Job
from src.settings import Settings
from src.worker.research import run_research
from src.worker.stream import run_chat

JOB_FAILED = "the job failed; the worker log has the details"
JOB_ABANDONED = "the job did not finish"

INTERNAL = Error(code="INTERNAL", message=JOB_FAILED)


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
        log = logger.bind(job_id=job.job_id, kind=job.kind)
        status = await submit.status_of(self._broker, job.job_id)
        state = (status or {}).get(keys.STATUS)
        if state in submit.FINISHED:
            log.warning("job.already_finished")
            return
        if state == keys.RUNNING:
            await self._redelivered(job)
            return
        await submit.mark(
            self._broker,
            job.job_id,
            self._ttl_s,
            **{keys.STATUS: keys.RUNNING, keys.STARTED_AT: submit.now()},
        )
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
        await self.finish(job, Error(code="JOB_ABANDONED", message=JOB_ABANDONED))

    async def finish(self, job: Job, outcome: Done | Error) -> None:
        await self.publish(job.job_id, outcome)
        await self._mark_finished(job.job_id, outcome.type, getattr(outcome, "code", None))

    async def _redelivered(self, job: Job) -> None:
        """A worker died (or lost the broker) mid-job. Its turn is not replayed."""
        last = await events.last_terminal(self._broker, job.job_id)
        if last is not None:
            code = json.loads(last.data).get("code") if last.type == "error" else None
            logger.bind(job_id=job.job_id).warning("job.finished_before_redelivery")
            await self._mark_finished(job.job_id, last.type, code)
            return
        logger.bind(job_id=job.job_id).error("job.interrupted")
        await self.finish(job, error_event(JobInterrupted()))

    async def _mark_finished(self, job_id: str, outcome: str, code: str | None) -> None:
        fields = {keys.STATUS: keys.DONE if outcome == "done" else keys.FAILED}
        if code is not None:
            fields[keys.ERROR_CODE] = code
        fields[keys.FINISHED_AT] = submit.now()
        await submit.mark(self._broker, job_id, self._ttl_s, **fields)

    async def _execute(self, job: Job) -> dict[str, Any]:
        user = job.user
        await self._app.record_signals(
            user, {"client": job.client.client, "channel": job.channel}, "gateway"
        )

        async def publish(event: Event) -> None:
            await self.publish(job.job_id, event)

        if job.kind == "research":
            return await run_research(self._app.pipeline, user, job.ticker, publish)
        lock = ThreadLock(
            self._broker,
            user,
            job.thread_id,
            self._settings.AGENT_LOCK_TTL_MS,
            self._settings.AGENT_LOCK_WAIT_MS,
        )
        async with lock.held():
            chat = run_chat(
                self._app.chat,
                user,
                job.thread_id,
                job.job_id,
                job.message,
                publish,
                secrets=await self._app.signal_values(user),
                stream_reasoning=self._settings.AGENT_STREAM_REASONING,
            )
            return await lock.guard(chat)
