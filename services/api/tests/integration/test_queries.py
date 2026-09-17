"""Every query the API runs, against a real database as `lauretta_app`: each user reads and
writes only their own rows, whatever the query names."""

import pytest

from src.db.pool import rows
from src.db.queries import facts, holdings, theses, threads

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mat_only")]


async def test_reads_return_the_callers_rows_only(pool):
    assert [h["ticker"] for h in await holdings.all_of(pool, "mat")] == ["NVDA"]
    assert await holdings.all_of(pool, "max") == []
    assert (await theses.latest(pool, "mat", "NVDA"))["advice"] == {"action": "buy"}
    assert await theses.latest(pool, "max", "NVDA") is None


async def test_the_voice_fact_is_the_callers_own(pool):
    assert await facts.tts_voice(pool, "mat") == "voice_mat"
    assert await facts.tts_voice(pool, "max") is None


async def test_threads_are_per_user(pool):
    assert await threads.create(pool, "max", "main", "test") is True
    assert await threads.create(pool, "mat", "main", "test") is False
    assert await threads.find_aliases(pool, "mat", ["alias-1"]) == {"alias-1": "main"}
    assert await threads.find_aliases(pool, "max", ["alias-1"]) == {}


async def test_aliases_added_by_max_stay_his(pool):
    await threads.create(pool, "max", "t-max", "test")
    await threads.add_aliases(pool, "max", "t-max", ["alias-max"])
    assert await threads.find_aliases(pool, "max", ["alias-max"]) == {"alias-max": "t-max"}
    assert await threads.find_aliases(pool, "mat", ["alias-max"]) == {}


async def test_a_query_naming_mat_in_max_scope_returns_nothing(pool):
    assert (
        await rows(pool, "max", "SELECT * FROM thread_aliases WHERE user_id = %s", ("mat",)) == []
    )
