"""The HTTP API (`uvicorn src.api.app:app`): queues jobs for the worker and reads results.

It opens the database pool for reads and the broker connection, and never runs a graph.
Authentication is the gateway's, the only container that can reach this API: it names the user
in `X-Lauretta-User` (see `deps.py`), and every read, job and thread is that user's alone.
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.api import events, jobs, reads
from src.api.mcpserver import server as mcp_server
from src.api.openai import routes as openai_routes
from src.api.openai.models import OpenAIError, error_response
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
            mcp_server.bound.settings, mcp_server.bound.broker = settings, broker
            mcp_server.bound.pool = pool
            async with mcp_server.mcp.session_manager.run():
                yield
    finally:
        await broker.aclose()


def create_app(with_lifespan: bool = True) -> FastAPI:
    """Tests build it without the lifespan and set `app.state` themselves."""
    api = FastAPI(title="Lauretta Stocks", lifespan=lifespan if with_lifespan else None)
    for module in (jobs, events, reads, openai_routes):
        api.include_router(module.router)
    api.add_exception_handler(OpenAIError, error_response)
    # The MCP server (Goose and other MCP clients); its session manager runs in `lifespan`.
    api.mount("/mcp", mcp_server.mcp.streamable_http_app())
    return api


app = create_app()
