"""What we know about the investor, rendered as prompt blocks. Read fresh on every step."""

from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.db.queries import facts, holdings, memories, theses
from src.memory.topics import CORE_TOPICS, TOPICS
from src.persona.layers import (
    ADVISOR_USER_KEYS,
    build_persona,
    desk_names,
    render_fields,
    render_persona,
    unnamed,
)
from src.prompts import blocks

PER_TOPIC = 3
THESES_IN_PROMPT = 10


async def investor_blocks(pool: AsyncConnectionPool, user_id: str) -> tuple[str, list[str]]:
    """The `<investor>` and `<holdings>` blocks, and the core topics still unknown."""
    remembered = await memories.by_topic(pool, user_id, PER_TOPIC)
    positions = await holdings.all_of(pool, user_id)
    unknown = unknown_topics(remembered)
    blocks = "\n".join([render_investor(remembered), render_holdings(positions)])
    return blocks, unknown


async def persona_blocks(
    pool: AsyncConnectionPool, user_id: str
) -> tuple[str, list[str], dict[str, str]]:
    """The `<soul>`, `<identity>`, `<user>` and `<signals>` blocks, the names still unknown and
    the desk's current names."""
    persona = build_persona(await facts.persona_rows(pool, user_id))
    return render_persona(persona), unnamed(persona), desk_names(persona)


async def names_of_desk(pool: AsyncConnectionPool, user_id: str) -> dict[str, str]:
    """Each desk agent's current name, by name key."""
    return desk_names(build_persona(await facts.persona_rows(pool, user_id)))


async def advisor_user_block(pool: AsyncConnectionPool, user_id: str) -> str:
    """The investor's name, country and currency; nothing about the assistant."""
    persona = build_persona(await facts.persona_rows(pool, user_id))
    return render_fields("user", persona.user, ADVISOR_USER_KEYS)


async def theses_block(pool: AsyncConnectionPool, user_id: str) -> str:
    saved = await theses.recent(pool, user_id, THESES_IN_PROMPT)
    lines = [blocks.THESIS_LINE.format(**t) for t in saved]
    return "<theses>\n" + ("\n".join(lines) or blocks.NO_THESES) + "\n</theses>"


def render_investor(remembered: list[dict[str, Any]]) -> str:
    """Up to three facts per topic, newest first, each with the date it was said."""
    lines = []
    for topic in TOPICS:
        facts = [m for m in remembered if m["topic"] == topic][:PER_TOPIC]
        lines.extend(blocks.INVESTOR_LINE.format(**m) for m in facts)
    return "<investor>\n" + ("\n".join(lines) or blocks.NO_INVESTOR_FACTS) + "\n</investor>"


def render_holdings(positions: list[dict[str, Any]]) -> str:
    lines = []
    for position in positions:
        cost = f" @ {position['avg_cost']:g}" if position["avg_cost"] else ""
        note = f" ({position['note']})" if position["note"] else ""
        lines.append(f"{position['ticker']}: {position['shares']:g} shares{cost}{note}")
    return "<holdings>\n" + ("\n".join(lines) or blocks.NO_HOLDINGS) + "\n</holdings>"


def unknown_topics(remembered: list[dict[str, Any]]) -> list[str]:
    known = {m["topic"] for m in remembered}
    return [topic for topic in CORE_TOPICS if topic not in known]
