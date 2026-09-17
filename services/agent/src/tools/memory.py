"""Tools over the investor's long-term memory."""

from typing import Any

from langchain_core.tools import BaseTool, tool
from psycopg_pool import AsyncConnectionPool

from src.db.queries import memories
from src.memory.embedder import Embedder
from src.tools.models import ForgetArgs, RecallArgs, RememberArgs


def build_remember(pool: AsyncConnectionPool, embedder: Embedder, user_id: str) -> BaseTool:
    @tool(args_schema=RememberArgs)
    async def remember(topic: str, content: str) -> dict[str, Any]:
        """Save one fact the investor told you about themselves, their goals, their rules or
        how they like to work. One fact per call. When a fact replaces an older one, save the
        new one and forget the old one.
        """
        saved = await memories.add(pool, embedder, user_id, topic, content)
        return {"remembered": True, **saved}

    return remember


def build_recall(pool: AsyncConnectionPool, embedder: Embedder, user_id: str) -> BaseTool:
    @tool(args_schema=RecallArgs)
    async def recall(query: str, limit: int = 5) -> dict[str, Any]:
        """Search what the investor has told us (memories and profile), best match first by
        meaning, then exact words, with newer facts slightly ahead, and the date each was said.
        Older facts may be out of date.
        """
        return {"memories": await memories.search(pool, embedder, user_id, query, limit)}

    return recall


def build_forget(pool: AsyncConnectionPool, user_id: str) -> BaseTool:
    @tool(args_schema=ForgetArgs)
    async def forget(memory_id: str) -> dict[str, Any]:
        """Delete a memory that the investor says is wrong or no longer true."""
        return {"forgotten": await memories.delete(pool, user_id, memory_id)}

    return forget
