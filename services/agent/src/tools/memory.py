"""Tools over the investor's long-term memory, for the user the run acts for."""

from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from src.db.queries import memories
from src.graph.ctx import Ctx, user_of
from src.memory.embedder import Embedder
from src.tools.scoped import ScopedForgetArgs, ScopedRecallArgs, ScopedRememberArgs


def build_remember(pool: AsyncConnectionPool, embedder: Embedder) -> BaseTool:
    @tool(args_schema=ScopedRememberArgs)
    async def remember(topic: str, content: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """Save one fact the investor told you about themselves, their goals, their rules or
        how they like to work. One fact per call. When a fact replaces an older one, save the
        new one and forget the old one.
        """
        saved = await memories.add(pool, embedder, user_of(runtime.context), topic, content)
        return {"remembered": True, **saved}

    return remember


def build_recall(
    pool: AsyncConnectionPool,
    embedder: Embedder,
    kinds: tuple[str, ...] = memories.MEMORIES_AND_PROFILE,
) -> BaseTool:
    """`kinds`: what the search reaches; the Strategist's recall reaches memories only."""

    @tool(args_schema=ScopedRecallArgs)
    async def recall(query: str, runtime: ToolRuntime[Ctx], limit: int = 5) -> dict[str, Any]:
        """Search what the investor has told us, best match first by meaning, then exact words,
        with newer facts slightly ahead, and the date each was said. Older facts may be out of
        date.
        """
        user_id = user_of(runtime.context)
        found = await memories.search(pool, embedder, user_id, query, limit, kinds)
        return {"memories": found}

    return recall


def build_forget(pool: AsyncConnectionPool) -> BaseTool:
    @tool(args_schema=ScopedForgetArgs)
    async def forget(memory_id: str, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """Delete a memory that the investor says is wrong or no longer true."""
        return {"forgotten": await memories.delete(pool, user_of(runtime.context), memory_id)}

    return forget
