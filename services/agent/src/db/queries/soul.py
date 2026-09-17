"""The assistant's soul on the facts table: proposals, and approving or rejecting them.

At most one soul row is active per investor. A proposal records the soul it would replace in
`supersedes` and its reason in `value`. Approving it applies only while that soul is still the
active one, so an old proposal never silently undoes a newer approved soul. Every write takes the
investor's persona lock (`facts.lock_persona`).
"""

from datetime import timedelta
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows, scoped
from src.db.queries.facts import lock_persona
from src.errors import PersonaInvalid
from src.memory.embedder import Embedder, vector_literal
from src.persona.soul import check_soul

PROPOSAL_NOT_PROPOSED = "soul proposal {proposal_id} is no longer proposed"

_ACTIVE = "SELECT id FROM facts WHERE user_id = %s AND kind = 'soul' AND status = 'active'"


async def propose(
    pool: AsyncConnectionPool,
    embedder: Embedder,
    user_id: str,
    text: str,
    reason: str,
    max_pending: int,
    max_age: timedelta,
) -> dict[str, str] | None:
    """Stores a soul as `proposed`, with its reason and the soul active now, and returns its id
    and the stored (stripped) content. Changes nothing active. None, storing nothing, while
    `max_pending` proposals younger than `max_age` already wait for a decision."""
    content = check_soul(text)
    vector = vector_literal(await embedder.embed(content))
    async with scoped(pool, user_id) as conn:
        await lock_persona(conn, user_id)
        (pending,) = await (
            await conn.execute(
                """SELECT count(*) AS n FROM facts
                   WHERE user_id = %s AND kind = 'soul' AND status = 'proposed'
                     AND created_at > now() - %s""",
                (user_id, max_age),
            )
        ).fetchall()
        if pending["n"] >= max_pending:
            return None
        current = await (await conn.execute(_ACTIVE, (user_id,))).fetchall()
        cursor = await conn.execute(
            """INSERT INTO facts (user_id, subject, kind, content, value, embedding, source,
                                  status, supersedes)
               VALUES (%s, 'assistant', 'soul', %s, %s, %s::vector, 'chat', 'proposed', %s)
               RETURNING id::text, content""",
            (user_id, content, Jsonb({"reason": reason}), vector,
             current[0]["id"] if current else None),
        )  # fmt: skip
        (saved,) = await cursor.fetchall()
    return saved


async def matching(pool: AsyncConnectionPool, user_id: str, short_id: str) -> list[dict[str, Any]]:
    """Soul rows whose id starts with `short_id` (lowercase hex and dashes, checked by the
    caller)."""
    return await rows(
        pool,
        user_id,
        """SELECT id::text, status, value->>'reason' AS reason, created_at FROM facts
           WHERE user_id = %s AND kind = 'soul' AND id::text LIKE %s""",
        (user_id, f"{short_id}%"),
    )


async def approve(pool: AsyncConnectionPool, user_id: str, proposal_id: str) -> bool:
    """Makes the proposal the active soul. False, changing nothing, when the active soul is no
    longer the one the proposal was written against (stale)."""
    async with scoped(pool, user_id) as conn:
        await lock_persona(conn, user_id)
        found = await (
            await conn.execute(
                """SELECT supersedes FROM facts
                   WHERE user_id = %s AND id::text = %s AND kind = 'soul'
                     AND status = 'proposed'""",
                (user_id, proposal_id),
            )
        ).fetchall()
        if not found:
            raise PersonaInvalid(PROPOSAL_NOT_PROPOSED.format(proposal_id=proposal_id))
        current = await (await conn.execute(_ACTIVE, (user_id,))).fetchall()
        previous = current[0]["id"] if current else None
        if found[0]["supersedes"] != previous:
            return False
        if previous is not None:
            await conn.execute("UPDATE facts SET status = 'superseded' WHERE id = %s", (previous,))
        await conn.execute(
            "UPDATE facts SET status = 'active' WHERE user_id = %s AND id::text = %s",
            (user_id, proposal_id),
        )
    return True


async def reject(pool: AsyncConnectionPool, user_id: str, proposal_id: str) -> None:
    rejected = await rows(
        pool,
        user_id,
        """UPDATE facts SET status = 'rejected'
           WHERE user_id = %s AND id::text = %s AND kind = 'soul' AND status = 'proposed'
           RETURNING id""",
        (user_id, proposal_id),
    )
    if not rejected:
        raise PersonaInvalid(PROPOSAL_NOT_PROPOSED.format(proposal_id=proposal_id))
