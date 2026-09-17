"""Tools over the persona: the assistant's identity, the investor's profile, soul proposals."""

from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from src.db.queries import facts, soul
from src.graph.ctx import Ctx, user_of
from src.memory.embedder import Embedder
from src.memory.keys import SETUP_SKIPS, SKIPPED, SkippableStep
from src.persona.approval import SHORT_ID_CHARS
from src.tools.scoped import (
    ScopedProposeSoulArgs,
    ScopedSetIdentityArgs,
    ScopedSetUserDetailsArgs,
    ScopedSkipSetupStepArgs,
)


def build_set_identity(pool: AsyncConnectionPool, embedder: Embedder) -> BaseTool:
    @tool(args_schema=ScopedSetIdentityArgs)
    async def set_identity(
        runtime: ToolRuntime[Ctx],
        name: str | None = None,
        emoji: str | None = None,
        vibe: str | None = None,
        analyst_name: str | None = None,
        checker_name: str | None = None,
        strategist_name: str | None = None,
    ) -> dict[str, Any]:
        """Set how the desk presents itself: your name, emoji or vibe, and the names of the
        Analyst, the Checker and the Strategist. Only save names the investor chose or
        confirmed, never invented ones; one call can rename several agents. Fields you leave
        out stay as they are.
        """
        values = {
            "bot_name": name,
            "bot_emoji": emoji,
            "bot_vibe": vibe,
            "analyst_name": analyst_name,
            "checker_name": checker_name,
            "strategist_name": strategist_name,
        }
        saved = await facts.set_many(
            pool, embedder, user_of(runtime.context), "identity", values, "chat"
        )
        return {"saved": True, **saved}

    return set_identity


def build_set_user_details(pool: AsyncConnectionPool, embedder: Embedder) -> BaseTool:
    @tool(args_schema=ScopedSetUserDetailsArgs)
    async def set_user_details(
        runtime: ToolRuntime[Ctx],
        name: str | None = None,
        preferred_name: str | None = None,
        city: str | None = None,
        country: str | None = None,
        currency: str | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Record the investor's name, what they want to be called, their city, country,
        currency or timezone, as they told you. Fields you leave out stay as they are.
        """
        values = {
            "name": name,
            "preferred_name": preferred_name,
            "city": city,
            "country": country,
            "currency": currency.upper() if currency else None,
            "timezone": timezone,
        }
        saved = await facts.set_many(
            pool, embedder, user_of(runtime.context), "profile", values, "chat"
        )
        return {"saved": True, **saved}

    return set_user_details


def build_skip_setup_step(pool: AsyncConnectionPool, embedder: Embedder) -> BaseTool:
    @tool(args_schema=ScopedSkipSetupStepArgs)
    async def skip_setup_step(step: SkippableStep, runtime: ToolRuntime[Ctx]) -> dict[str, Any]:
        """Mark an optional setup step skipped so it is never asked again. Only when the
        investor said so: they keep the team's names, or have no holdings to record.
        """
        user_id = user_of(runtime.context)
        await facts.set_keyed(pool, embedder, user_id, SETUP_SKIPS[step], SKIPPED, "chat")
        return {"skipped": step}

    return skip_setup_step


def build_propose_soul_change(pool: AsyncConnectionPool, embedder: Embedder) -> BaseTool:
    @tool(args_schema=ScopedProposeSoulArgs)
    async def propose_soul_change(
        content: str, reason: str, runtime: ToolRuntime[Ctx]
    ) -> dict[str, Any]:
        """Propose a new soul: your persona, voice and boundaries. Write the full new text.
        This changes nothing yet: the investor sees the proposal and the phrase to approve it
        under your reply, and only their reply applies it. Never say it has been applied.
        """
        user_id = user_of(runtime.context)
        proposal_id = await soul.propose(pool, embedder, user_id, content, reason)
        return {
            "proposed": True,
            "applied": False,
            "proposal_id": proposal_id[:SHORT_ID_CHARS],
            "reason": reason,
            "content": content,
        }

    return propose_soul_change
