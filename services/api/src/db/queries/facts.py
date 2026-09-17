"""The facts the API reads directly: the user's chosen voice. The worker owns every write."""

from psycopg_pool import AsyncConnectionPool

from src.db.pool import rows


async def tts_voice(pool: AsyncConnectionPool, user_id: str) -> str | None:
    """The active `tts_voice` identity fact, if the user chose one."""
    found = await rows(
        pool,
        user_id,
        """SELECT value FROM facts
           WHERE user_id = %s AND subject = 'assistant' AND key = 'tts_voice'
             AND status = 'active'""",
        (user_id,),
    )
    value = found[0]["value"] if found else None
    return value if isinstance(value, str) and value else None
