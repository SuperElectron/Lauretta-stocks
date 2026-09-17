"""`python -m src.worker`: consumes jobs until SIGTERM or SIGINT, then drains running ones."""

import asyncio
import os
import signal
import socket
import sys

from loguru import logger

from src.app import open_app
from src.errors import AgentError
from src.queue.broker import connect
from src.queue.consumer import Consumer
from src.runs import QueuedRuns
from src.settings import Settings
from src.worker.handler import JobHandler


async def main() -> None:
    settings = Settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)

    broker = connect(settings.broker_url())
    name = f"{socket.gethostname()}-{os.getpid()}"
    try:
        await broker.ping()
        # Research the desk starts for itself goes on the same queue, for any worker to run.
        async with open_app(settings, QueuedRuns(broker, settings.EVENTS_TTL_S)) as app:
            consumer = Consumer(
                broker,
                JobHandler(app, broker, settings),
                name,
                concurrency=settings.WORKER_CONCURRENCY,
                min_idle_ms=settings.BROKER_MIN_IDLE_MS,
                max_deliveries=settings.BROKER_MAX_DELIVERIES,
            )
            logger.bind(consumer=name).info("worker.started")
            await consumer.run(stop)
    except AgentError as exc:
        sys.exit(f"{exc.code}: {exc.message}")
    finally:
        await broker.aclose()
    logger.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
