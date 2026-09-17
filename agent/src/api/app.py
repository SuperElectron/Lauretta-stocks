"""The HTTP API (`uvicorn src.api.app:app`): queues jobs for the worker and reads results.

It opens the database pool for reads and the broker connection, and never runs a graph.
Authentication is the gateway's; the API trusts the headers it forwards.
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.api import events, jobs, reads
from src.db.pool import open_pool
from src.queue.broker import connect
from src.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)
    broker = connect(settings.broker_url())
    try:
        async with open_pool(
            settings.DATABASE_URL, min_size=settings.DB_POOL_MIN, max_size=settings.DB_POOL_MAX
        ) as pool:
            app.state.settings, app.state.broker, app.state.pool = settings, broker, pool
            yield
    finally:
        await broker.aclose()


def create_app(with_lifespan: bool = True) -> FastAPI:
    """Tests build it without the lifespan and set `app.state` themselves."""
    api = FastAPI(title="Lauretta Stocks", lifespan=lifespan if with_lifespan else None)
    for module in (jobs, events, reads):
        api.include_router(module.router)
    return api


app = create_app()
