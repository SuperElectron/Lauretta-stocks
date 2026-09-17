"""Row-level security as the app role: one user never reads, changes or writes another's rows,
even when a query names the other user, and a query outside a user's scope sees nothing."""

import psycopg
import pytest

from src.db.checkpointer import build_checkpointer
from src.db.pool import rows, scoped
from src.db.queries import holdings, memories, theses, threads
from src.errors import DatabaseUnavailable
from tests.integration.conftest import OWNER_URL, SETUP_URL, TABLES, VECTOR

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mat_only")]


class FixedEmbedder:
    """Embeds every text as the seeded vector, so a search matches Mat's memory exactly."""

    async def embed(self, _text: str) -> list[float]:
        return [float(v) for v in VECTOR.strip("[]").split(",")]


async def test_the_app_role_is_no_superuser_and_cannot_bypass_rls(pool):
    (role,) = await rows(
        pool, "max", "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert role == {"rolsuper": False, "rolbypassrls": False}


async def test_every_user_table_forces_rls(pool):
    found = await rows(
        pool,
        "max",
        """SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
           WHERE relname = ANY(%s)""",
        (list(TABLES),),
    )
    assert {r["relname"]: (r["relrowsecurity"], r["relforcerowsecurity"]) for r in found} == {
        table: (True, True) for table in TABLES
    }


@pytest.mark.parametrize("table", TABLES)
async def test_max_reads_changes_and_deletes_none_of_mats_rows(pool, table):
    async with scoped(pool, "max") as conn:
        seen = await (await conn.execute(f"SELECT * FROM {table} WHERE user_id = 'mat'")).fetchall()
        updated = await conn.execute(f"UPDATE {table} SET user_id = 'max' WHERE user_id = 'mat'")
        deleted = await conn.execute(f"DELETE FROM {table} WHERE user_id = 'mat'")
        assert (seen, updated.rowcount, deleted.rowcount) == ([], 0, 0)
    (count,) = await rows(pool, "mat", f"SELECT count(*) AS n FROM {table}")
    assert count["n"] == 1


@pytest.mark.parametrize(
    "insert",
    [
        "INSERT INTO holdings (user_id, ticker, shares) VALUES ('mat', 'X', 1)",
        "INSERT INTO threads (user_id, thread_id, client) VALUES ('mat', 'x', 'test')",
        """INSERT INTO theses (user_id, ticker, story, review, advice, revisions)
           VALUES ('mat', 'X', '{}', '{}', '{}', 0)""",
    ],
)
async def test_max_cannot_write_a_row_as_mat(pool, insert):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await rows(pool, "max", insert)


async def test_max_own_write_works_and_stays_his(pool):
    await holdings.upsert(pool, "max", "AAPL", 5, None, None)
    assert [h["ticker"] for h in await holdings.all_of(pool, "max")] == ["AAPL"]
    assert [h["ticker"] for h in await holdings.all_of(pool, "mat")] == ["NVDA"]


@pytest.mark.parametrize("table", TABLES)
async def test_a_query_outside_any_scope_sees_nothing(pool, table):
    async with pool.connection() as conn:
        found = await (await conn.execute(f"SELECT count(*) AS n FROM {table}")).fetchone()
    assert found["n"] == 0


async def test_a_reused_connection_carries_no_user(pool):
    assert await holdings.all_of(pool, "mat")
    async with pool.connection() as conn:
        setting = await (
            await conn.execute("SELECT current_setting('app.user_id', true) AS user_id")
        ).fetchone()
        assert setting["user_id"] in (None, "")
        visible = await (await conn.execute("SELECT count(*) AS n FROM holdings")).fetchone()
        assert visible["n"] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("INSERT INTO holdings (user_id, ticker, shares) VALUES ('', 'X', 1)")


async def test_a_query_naming_mat_in_max_scope_returns_nothing(pool):
    assert await rows(pool, "max", "SELECT * FROM holdings WHERE user_id = %s", ("mat",)) == []
    assert await theses.latest(pool, "max", "NVDA") is None
    assert await threads.find_aliases(pool, "max", ["alias-1"]) == {}


async def test_memory_search_as_max_never_returns_mats_identical_memory(pool):
    embedder = FixedEmbedder()
    assert await memories.search(pool, embedder, "max", "I hate risk", 5) == []
    assert [m["content"] for m in await memories.search(pool, embedder, "mat", "I hate risk", 5)]
    # The same memory added by Max is his own row, not a duplicate of Mat's.
    added = await memories.add(pool, embedder, "max", "risk_tolerance", "I hate risk")
    assert added["deduped"] is False


async def test_a_thread_id_mat_uses_is_a_separate_thread_for_max(pool):
    assert await threads.create(pool, "max", "main", "test") is True
    assert await threads.create(pool, "mat", "main", "test") is False


async def test_checkpoint_tables_are_created_by_the_migrator_and_used_by_the_app(pool):
    await build_checkpointer(pool, SETUP_URL)
    assert await rows(pool, "max", "SELECT thread_id FROM checkpoints LIMIT 1") == []
    with psycopg.connect(OWNER_URL) as conn:
        (owner,) = conn.execute(
            "SELECT tableowner FROM pg_tables WHERE tablename = 'checkpoints'"
        ).fetchone()
    assert owner == "lauretta_migrator"
    # The worker, without the migrator, only checks the tables are current, and refuses to start
    # when they are not; running the migration again (as every deploy does) fixes that.
    await build_checkpointer(pool)
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        conn.execute(
            "DELETE FROM checkpoint_migrations WHERE v = (SELECT max(v) FROM checkpoint_migrations)"
        )
    with pytest.raises(DatabaseUnavailable):
        await build_checkpointer(pool)
    await build_checkpointer(pool, SETUP_URL)
    await build_checkpointer(pool)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await rows(pool, "max", "CREATE TABLE sneaky (id int)")


def test_the_migrator_is_no_superuser_and_reads_no_user_data():
    with psycopg.connect(SETUP_URL, autocommit=True) as conn:
        flags = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert flags == (False, False)
        for table in TABLES:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT 1 FROM {table}")
