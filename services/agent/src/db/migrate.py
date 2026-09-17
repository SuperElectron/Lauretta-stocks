"""`python -m src.db.migrate`: creates the checkpoint tables and exits.

A deploy step, never part of a long-running service: the compose `migrate` service (profile
`migrate`) runs it as `lauretta_migrator` before the stack starts, from `just deploy` and from
`services/db/reset-and-restore.sh`. The worker only checks the tables are current.
"""

import asyncio
import sys

from src.db.checkpointer import create_tables
from src.errors import AgentError
from src.settings import Settings


async def main() -> None:
    settings = Settings()
    try:
        await create_tables(settings.DATABASE_SETUP_URL or settings.DATABASE_URL)
    except AgentError as exc:
        sys.exit(f"{exc.code}: {exc.message}")


if __name__ == "__main__":
    asyncio.run(main())
