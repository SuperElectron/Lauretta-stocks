"""What we know about the investor, rendered as prompt blocks. Read fresh on every step."""

from dataclasses import dataclass
from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.db.queries import facts, holdings, memories, theses
from src.memory.topics import CORE_TOPICS, TOPICS
from src.persona.layers import (
    ADVISOR_USER_KEYS,
    Persona,
    build_persona,
    render_fields,
)
from src.prompts import blocks

PER_TOPIC = 3
THESES_IN_PROMPT = 10


@dataclass(frozen=True)
class Known:
    """Everything a turn or a research run knows about the investor, read once."""

    persona: Persona
    # The newest few memories per topic.
    remembered: list[dict[str, Any]]
    positions: list[dict[str, Any]]


async def load_known(pool: AsyncConnectionPool, user_id: str) -> Known:
    return Known(
        persona=build_persona(await facts.persona_rows(pool, user_id)),
        remembered=await memories.by_topic(pool, user_id, PER_TOPIC),
        positions=await holdings.all_of(pool, user_id),
    )


def investor_blocks(known: Known) -> str:
    """The `<investor>` and `<holdings>` blocks."""
    return "\n".join([render_investor(known.remembered), render_holdings(known.positions)])


def advisor_user_block(known: Known) -> str:
    """The investor's name, country and currency; nothing about the assistant."""
    return render_fields("user", known.persona.user, ADVISOR_USER_KEYS)


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
