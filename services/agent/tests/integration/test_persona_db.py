"""The persona queries on a real database as `lauretta_app`: keyed facts supersede under the
persona lock, soul proposals are capped and stored stripped, approval never undoes a newer soul,
and hybrid search reaches only the kinds asked for."""

import asyncio

import pytest

from src.db.pool import open_pool, rows
from src.db.queries import facts, memories, soul
from src.errors import PersonaInvalid
from src.persona.approval import MAX_PENDING_PROPOSALS, PROPOSAL_MAX_AGE, decide
from tests.integration.conftest import APP_URL, VECTOR

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mat_only")]
USER = "max"


class FixedEmbedder:
    async def embed(self, _text: str) -> list[float]:
        return [float(v) for v in VECTOR.strip("[]").split(",")]


EMBEDDER = FixedEmbedder()


async def keyed_rows(pool, key: str) -> list[dict]:
    return await rows(
        pool,
        USER,
        """SELECT id::text, value, status, supersedes::text FROM facts
           WHERE user_id = %s AND key = %s ORDER BY created_at""",
        (USER, key),
    )


async def souls(pool) -> dict[str, str]:
    found = await rows(
        pool,
        USER,
        "SELECT id::text, status FROM facts WHERE user_id = %s AND kind = 'soul'",
        (USER,),
    )
    return {r["id"]: r["status"] for r in found}


async def propose(pool, text: str = "Warm.") -> dict | None:
    return await soul.propose(
        pool, EMBEDDER, USER, text, "warmer", MAX_PENDING_PROPOSALS, PROPOSAL_MAX_AGE
    )


async def test_set_keyed_supersedes_and_keeps_history(pool):
    first = await facts.set_keyed(pool, EMBEDDER, USER, "checker_name", "Ivy", "chat")
    same = await facts.set_keyed(pool, EMBEDDER, USER, "checker_name", "Ivy", "chat")
    second = await facts.set_keyed(pool, EMBEDDER, USER, "checker_name", "Max", "chat")
    assert (first["changed"], same["changed"], second["changed"]) == (True, False, True)
    old, new = await keyed_rows(pool, "checker_name")
    assert (old["status"], new["status"], new["supersedes"]) == ("superseded", "active", old["id"])


async def test_concurrent_writes_to_one_key_leave_one_active_row():
    async with open_pool(APP_URL, min_size=4, max_size=4) as wide:
        names = [f"Name{i}" for i in range(8)]
        await asyncio.gather(
            *(facts.set_keyed(wide, EMBEDDER, USER, "analyst_name", n, "chat") for n in names)
        )
        found = await keyed_rows(wide, "analyst_name")
    assert [r["status"] for r in found].count("active") == 1
    assert len(found) == len(names)


async def test_set_many_refuses_wrong_keys_and_writes_each_given_one(pool):
    with pytest.raises(PersonaInvalid):
        await facts.set_many(pool, EMBEDDER, USER, "signal", {"channel": "cli", "x": "y"}, "cli")
    await facts.set_many(pool, EMBEDDER, USER, "signal", {"channel": "cli", "ip": "1.2.3.4"}, "cli")
    assert len(await keyed_rows(pool, "channel")) == len(await keyed_rows(pool, "ip")) == 1


async def test_propose_stores_stripped_text_and_caps_pending(pool):
    saved = await propose(pool, "  Warm and brief.  ")
    assert saved["content"] == "Warm and brief."
    for _ in range(MAX_PENDING_PROPOSALS - 1):
        assert await propose(pool)
    assert await propose(pool) is None
    assert list((await souls(pool)).values()) == ["proposed"] * MAX_PENDING_PROPOSALS


async def test_approve_reject_and_a_stale_proposal(pool):
    first, second, third = [await propose(pool, f"Soul {n}.") for n in range(3)]
    assert (await decide(pool, USER, "approve", first["id"][:8]))["outcome"] == "approved"
    # Written against the default soul, which `first` has since replaced.
    stale = await decide(pool, USER, "approve", second["id"])
    assert stale["outcome"] == "stale"
    assert (await decide(pool, USER, "reject", third["id"][:8]))["outcome"] == "rejected"
    assert await souls(pool) == {
        first["id"]: "active",
        second["id"]: "proposed",
        third["id"]: "rejected",
    }
    with pytest.raises(PersonaInvalid):
        await soul.reject(pool, USER, third["id"])
    assert (await decide(pool, USER, "approve", third["id"][:8]))["outcome"] == "already rejected"
    # A proposal written against the active soul replaces it.
    fourth = await propose(pool, "Soul 4.")
    assert await soul.approve(pool, USER, fourth["id"]) is True
    assert (await souls(pool))[first["id"]] == "superseded"


async def test_search_reaches_only_the_kinds_asked_for(pool):
    await memories.add(pool, EMBEDDER, USER, "goals", "Retire at 55")
    await facts.set_keyed(pool, EMBEDDER, USER, "city", "Leeds", "chat")
    await facts.set_keyed(pool, EMBEDDER, USER, "setup_holdings", "skipped", "chat")
    await facts.set_keyed(pool, EMBEDDER, USER, "last_seen_city", "Leeds", "gateway")
    both = await memories.search(pool, EMBEDDER, USER, "Leeds retire", 10)
    only = await memories.search(pool, EMBEDDER, USER, "Leeds retire", 10, memories.MEMORIES)
    assert sorted(r["kind"] for r in both) == ["memory", "profile"]
    assert [r["content"] for r in only] == ["Retire at 55"]
    assert all(0 <= r["score"] <= 1 for r in both)
