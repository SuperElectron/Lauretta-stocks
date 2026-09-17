"""Long-term memory over the facts table: add (deduplicated), hybrid search, by topic, delete.

Memories are the investor's free-text facts (subject user, kind memory). Search reaches their
profile (name, city, currency...) too when asked, but never signals, setup skips or anything about
the assistant.
"""

import hashlib
from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows
from src.memory.embedder import Embedder, vector_literal
from src.memory.keys import SETUP_KEYS

# Hybrid ranking: meaning leads, exact words help (tickers, names, account types), newer facts
# edge ahead of older ones that may be out of date. The weights sum to 1.
SIMILARITY_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.2
RECENCY_WEIGHT = 0.1
# A fact this many days old gets half the recency boost of one said today.
RECENCY_HALF_LIFE_DAYS = 90
# What search may return: memories alone, or memories and the investor's profile.
MEMORIES = ("memory",)
MEMORIES_AND_PROFILE = ("memory", "profile")

_SEARCH = """WITH scored AS (
    SELECT id::text, kind, topic, key, content, created_at::date::text AS created,
           (1 - (embedding <=> %(vector)s::vector))::float AS similarity,
           -- normalization 32 maps the rank into 0..1
           ts_rank(content_tsv, websearch_to_tsquery('english', %(query)s), 32)::float AS keyword,
           power(0.5, extract(epoch FROM now() - created_at)::float / 86400 / %(half_life)s)
               AS recency
    FROM facts
    WHERE user_id = %(user_id)s AND subject = 'user' AND kind = ANY(%(kinds)s)
      AND status = 'active' AND NOT coalesce(key = ANY(%(hidden_keys)s), false)
  )
  SELECT id, kind, topic, key, content, created, round(similarity::numeric, 3)::float AS similarity,
         round((%(similarity_weight)s * similarity + %(keyword_weight)s * keyword
                + %(recency_weight)s * recency)::numeric, 3)::float AS score
  FROM scored ORDER BY score DESC LIMIT %(limit)s"""


def content_hash(topic: str, content: str) -> str:
    """Same topic and same words (ignoring case and spacing) is the same memory."""
    normalized = " ".join(content.lower().split())
    return hashlib.sha256(f"{topic}\n{normalized}".encode()).hexdigest()


async def add(
    pool: AsyncConnectionPool, embedder: Embedder, user_id: str, topic: str, content: str
) -> dict[str, Any]:
    """Stores a memory. Re-adding one already stored returns its id with `deduped: true`."""
    sha = content_hash(topic, content)
    inserted = await rows(
        pool,
        user_id,
        """INSERT INTO facts (user_id, subject, kind, topic, content, sha256, embedding, source)
           VALUES (%s, 'user', 'memory', %s, %s, %s, %s::vector, 'chat')
           ON CONFLICT (user_id, sha256) DO NOTHING RETURNING id""",
        (user_id, topic, content, sha, vector_literal(await embedder.embed(content))),
    )
    if inserted:
        return {"id": str(inserted[0]["id"]), "deduped": False}
    (existing,) = await rows(
        pool, user_id, "SELECT id FROM facts WHERE user_id = %s AND sha256 = %s", (user_id, sha)
    )
    return {"id": str(existing["id"]), "deduped": True}


async def search(
    pool: AsyncConnectionPool,
    embedder: Embedder,
    user_id: str,
    query: str,
    limit: int,
    kinds: tuple[str, ...] = MEMORIES_AND_PROFILE,
) -> list[dict[str, Any]]:
    """The investor's best-matching facts of `kinds` (only `memory` and `profile` exist to
    search), best first."""
    params = {
        "vector": vector_literal(await embedder.embed(query)),
        "query": query,
        "user_id": user_id,
        "half_life": RECENCY_HALF_LIFE_DAYS,
        "similarity_weight": SIMILARITY_WEIGHT,
        "keyword_weight": KEYWORD_WEIGHT,
        "recency_weight": RECENCY_WEIGHT,
        "limit": limit,
        "kinds": [kind for kind in kinds if kind in MEMORIES_AND_PROFILE],
        # Setup skips are bookkeeping for the setup flow, not something the investor said.
        "hidden_keys": list(SETUP_KEYS),
    }
    return await rows(pool, user_id, _SEARCH, params)


async def by_topic(pool: AsyncConnectionPool, user_id: str, per_topic: int) -> list[dict[str, Any]]:
    """The newest few memories on every topic, newest first. Needs no embedding."""
    return await rows(
        pool,
        user_id,
        """SELECT id, topic, content, created FROM (
             SELECT id::text, topic, content, created_at::date::text AS created, created_at,
                    row_number() OVER (PARTITION BY topic ORDER BY created_at DESC) AS rank
             FROM facts WHERE user_id = %s AND kind = 'memory'
           ) ranked WHERE rank <= %s ORDER BY created_at DESC""",
        (user_id, per_topic),
    )


async def delete(pool: AsyncConnectionPool, user_id: str, memory_id: str) -> bool:
    deleted = await rows(
        pool,
        user_id,
        "DELETE FROM facts WHERE user_id = %s AND kind = 'memory' AND id::text = %s RETURNING id",
        (user_id, memory_id),
    )
    return bool(deleted)
