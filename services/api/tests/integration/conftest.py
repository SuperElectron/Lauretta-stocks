"""The API's queries against a real Postgres built from `services/db/init`, as `lauretta_app`.

They need a fresh database and two URLs, and are skipped without them:
    RLS_TEST_OWNER_URL  the owner (superuser) that created the schema: seeds rows, checks setup
    RLS_TEST_APP_URL    `lauretta_app`, which the app connects as
`just test-db` starts a throwaway database in its own compose project, runs them and removes it.
"""

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg.types.json import Jsonb

from src.db.pool import open_pool

OWNER_URL = os.environ.get("RLS_TEST_OWNER_URL")
APP_URL = os.environ.get("RLS_TEST_APP_URL")
TABLES = ("facts", "holdings", "theses", "threads", "thread_aliases")
# The same content and vector for both users, so only row-level security tells them apart.
VECTOR = "[" + ",".join(["0.1"] * 384) + "]"

pytestmark = pytest.mark.integration


def pytest_collection_modifyitems(items):
    if OWNER_URL and APP_URL:
        return
    skip = pytest.mark.skip(reason="set RLS_TEST_OWNER_URL and _APP_URL (just test-db)")
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(skip)


def seed(user: str) -> None:
    """A memory, a voice fact, a holding, a thesis, a thread and an alias for `user`, written
    as the owner (a superuser, which row-level security does not apply to)."""
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO facts (user_id, subject, kind, topic, content, sha256, embedding, source)
               VALUES (%s, 'user', 'memory', 'risk_tolerance', 'I hate risk', %s, %s::vector,
                       'chat')""",
            (user, f"sha-{user}", VECTOR),
        )
        conn.execute(
            """INSERT INTO facts (user_id, subject, kind, key, content, value, embedding, source)
               VALUES (%s, 'assistant', 'identity', 'tts_voice', 'voice', %s, %s::vector,
                       'chat')""",
            (user, Jsonb(f"voice_{user}"), VECTOR),
        )
        conn.execute(
            """INSERT INTO holdings (user_id, ticker, shares) VALUES (%s, 'NVDA', 1000)""", (user,)
        )
        conn.execute(
            """INSERT INTO theses (user_id, ticker, story, review, advice, revisions)
               VALUES (%s, 'NVDA', %s, %s, %s, 0)""",
            (user, Jsonb({}), Jsonb({}), Jsonb({"action": "buy"})),
        )
        conn.execute(
            "INSERT INTO threads (user_id, thread_id, client) VALUES (%s, 'main', 'test')", (user,)
        )
        conn.execute(
            """INSERT INTO thread_aliases (user_id, alias_hash, thread_id)
               VALUES (%s, 'alias-1', 'main')""",
            (user,),
        )


@pytest.fixture
def mat_only() -> None:
    """A database holding the owner's rows alone."""
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(TABLES) + " CASCADE")
    seed("mat")


@pytest.fixture
async def pool() -> AsyncIterator:
    """The app's pool as `lauretta_app`, one connection, so every call reuses it."""
    async with open_pool(APP_URL, min_size=1, max_size=1) as opened:
        yield opened
