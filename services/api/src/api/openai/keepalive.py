"""A stream that also yields None while its source is quiet, so a response can send keep-alives."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from src.queue.events import StoredEvent


async def with_keepalive(
    source: AsyncIterator[StoredEvent], interval: float
) -> AsyncIterator[StoredEvent | None]:
    """Items from `source`, and None each time `interval` seconds pass without one."""
    end = object()

    async def following() -> Any:
        return await anext(source, end)

    pending = asyncio.create_task(following())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            item = pending.result()
            if item is end:
                return
            yield item
            pending = asyncio.create_task(following())
    finally:
        pending.cancel()
