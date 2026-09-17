"""`python -m src.db.migrate`: creates the checkpoint tables and exits.

The worker does the same at startup; the restore script (`services/db/restore.sh`) runs this
alone, so the tables exist before conversations are restored and before any job can run.
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
