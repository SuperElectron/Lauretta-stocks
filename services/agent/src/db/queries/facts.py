"""Keyed facts (identity, profile, signals) and the assistant's soul, on the facts table.

A keyed fact has one active row per (user, subject, key); setting a different value supersedes
the old row and keeps it. Setting the same value writes nothing, so per-request signals stay cheap.
"""

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows, scoped
from src.errors import PersonaInvalid
from src.memory.embedder import Embedder, vector_literal
from src.memory.keys import KEYS, KeyedKind, Source
from src.prompts import errors as wording

# Where signals may come from: the request itself, never a model tool.
SIGNAL_SOURCES: tuple[Source, ...] = ("gateway", "client", "cli")


async def persona_rows(pool: AsyncConnectionPool, user_id: str) -> list[dict[str, Any]]:
    """Every active identity, profile, signal and soul row for the investor."""
    return await rows(
        pool,
        user_id,
        """SELECT id::text, kind, key, content, value, created_at::date::text AS created
           FROM facts WHERE user_id = %s AND status = 'active'
             AND kind IN ('identity', 'profile', 'signal', 'soul')""",
        (user_id,),
    )


async def set_keyed(
    pool: AsyncConnectionPool,
    embedder: Embedder,
    user_id: str,
    key: str,
    value: str,
    source: Source,
) -> dict[str, Any]:
    """Makes `value` the active value of `key`. Unchanged values write nothing."""
    spec = KEYS[key]
    current = await rows(
        pool,
        user_id,
        """SELECT id, value FROM facts
           WHERE user_id = %s AND subject = %s AND key = %s AND status = 'active'""",
        (user_id, spec.subject, key),
    )
    if current and current[0]["value"] == value:
        return {"id": str(current[0]["id"]), "changed": False}
    content = spec.sentence.format(value)
    vector = vector_literal(await embedder.embed(content))
    previous = current[0]["id"] if current else None
    async with scoped(pool, user_id) as conn:
        if previous is not None:
            await conn.execute("UPDATE facts SET status = 'superseded' WHERE id = %s", (previous,))
        cursor = await conn.execute(
            """INSERT INTO facts (user_id, subject, kind, key, content, value, embedding, source,
                                  supersedes)
               VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s) RETURNING id::text""",
            (user_id, spec.subject, spec.kind, key, content, Jsonb(value), vector, source,
             previous),
        )  # fmt: skip
        (saved,) = await cursor.fetchall()
    return {"id": saved["id"], "changed": True}


async def set_many(
    pool: AsyncConnectionPool,
    embedder: Embedder,
    user_id: str,
    kind: KeyedKind,
    values: dict[str, str | None],
    source: Source,
) -> dict[str, str]:
    """Sets every non-None value; each key must be of `kind`. Returns what was given."""
    given = {key: value for key, value in values.items() if value is not None}
    wrong = [key for key in given if key not in KEYS or KEYS[key].kind != kind]
    if wrong:
        raise PersonaInvalid(wording.NOT_KEYS_OF_KIND.format(kind=kind, keys=", ".join(wrong)))
    for key, value in given.items():
        await set_keyed(pool, embedder, user_id, key, value, source)
    return given


async def record_signals(
    pool: AsyncConnectionPool,
    embedder: Embedder,
    user_id: str,
    signals: dict[str, str | None],
    source: Source,
) -> None:
    """Called by code on each request (API, CLI) with what it knows: ip, client, channel,
    last_seen_city. Only changed values are written."""
    if source not in SIGNAL_SOURCES:
        raise PersonaInvalid(
            wording.SIGNAL_SOURCE.format(sources=", ".join(SIGNAL_SOURCES), source=source)
        )
    await set_many(pool, embedder, user_id, "signal", signals, source)
