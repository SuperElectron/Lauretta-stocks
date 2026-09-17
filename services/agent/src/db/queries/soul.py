"""The assistant's soul on the facts table: proposals, and approving or rejecting them.

At most one soul row is active per investor. A proposal records the soul it would replace in
`supersedes` and its reason in `value`; approving it supersedes whatever is active then, in one
transaction.
"""

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows
from src.errors import PersonaInvalid
from src.memory.embedder import Embedder, vector_literal
from src.persona.soul import check_soul
from src.prompts import errors as wording

_ACTIVE = "SELECT id FROM facts WHERE user_id = %s AND kind = 'soul' AND status = 'active'"


async def propose(
    pool: AsyncConnectionPool, embedder: Embedder, user_id: str, text: str, reason: str
) -> str:
    """Stores a soul as `proposed`, with its reason and the soul active now. Changes nothing."""
    content = check_soul(text)
    vector = vector_literal(await embedder.embed(content))
    current = await rows(pool, _ACTIVE, (user_id,))
    (saved,) = await rows(
        pool,
        """INSERT INTO facts (user_id, subject, kind, content, value, embedding, source, status,
                              supersedes)
           VALUES (%s, 'assistant', 'soul', %s, %s, %s::vector, 'chat', 'proposed', %s)
           RETURNING id::text""",
        (user_id, content, Jsonb({"reason": reason}), vector,
         current[0]["id"] if current else None),
    )  # fmt: skip
    return saved["id"]


async def matching(pool: AsyncConnectionPool, user_id: str, short_id: str) -> list[dict[str, Any]]:
    """Soul rows whose id starts with `short_id` (lowercase hex, checked by the caller)."""
    return await rows(
        pool,
        """SELECT id::text, status, value->>'reason' AS reason, created_at FROM facts
           WHERE user_id = %s AND kind = 'soul' AND id::text LIKE %s""",
        (user_id, f"{short_id}%"),
    )


async def approve(pool: AsyncConnectionPool, user_id: str, proposal_id: str) -> None:
    async with pool.connection() as conn, conn.transaction():
        current = await (await conn.execute(_ACTIVE, (user_id,))).fetchall()
        previous = current[0]["id"] if current else None
        if previous is not None:
            await conn.execute("UPDATE facts SET status = 'superseded' WHERE id = %s", (previous,))
        cursor = await conn.execute(
            """UPDATE facts SET status = 'active', supersedes = %s
               WHERE user_id = %s AND id::text = %s AND kind = 'soul' AND status = 'proposed'
               RETURNING id""",
            (previous, user_id, proposal_id),
        )
        if not await cursor.fetchall():
            raise PersonaInvalid(wording.PROPOSAL_NOT_PROPOSED.format(proposal_id=proposal_id))


async def reject(pool: AsyncConnectionPool, user_id: str, proposal_id: str) -> None:
    rejected = await rows(
        pool,
        """UPDATE facts SET status = 'rejected'
           WHERE user_id = %s AND id::text = %s AND kind = 'soul' AND status = 'proposed'
           RETURNING id""",
        (user_id, proposal_id),
    )
    if not rejected:
        raise PersonaInvalid(wording.PROPOSAL_NOT_PROPOSED.format(proposal_id=proposal_id))
