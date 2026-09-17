"""Two investors' data in memory, behind the query functions the graphs and tools call.

Each fake answers only with the rows of the user it is asked for, the way the real queries (and
row-level security) do, and records that user: a test then proves every read and write of a run
was for the run's own user.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from src.data import market
from src.db.queries import facts, holdings, memories, soul, theses

MATS_PROPOSAL = "3f2a1b9c0d0e4f5a8b7c6d5e4f3a2b1c"
MATS_MEMORY = "mem-mat-1"


class TwoUsers:
    def __init__(self) -> None:
        self.users: list[str] = []
        self.holdings = {"mat": [{"ticker": "NVDA", "shares": 1000.0, "avg_cost": 5.0,
                                  "note": "Mat's secret position", "updated": "2026-09-01"}],
                         "max": []}  # fmt: skip
        self.memories = {
            "mat": [{"id": MATS_MEMORY, "kind": "memory", "topic": "risk_tolerance", "key": None,
                     "content": "Mat hates risk", "created": "2026-09-01"}],
            "max": [],
        }  # fmt: skip
        self.theses = {"mat": [{"ticker": "NVDA", "story": {"secret": "Mat's story"},
                                "review": {}, "advice": {"action": "buy"}, "revisions": 0,
                                "created": "2026-09-01"}],
                       "max": []}  # fmt: skip
        self.proposals = {
            "mat": [{"id": MATS_PROPOSAL, "status": "proposed", "reason": "Mat's reason",
                     "created_at": datetime.now(UTC)}],
            "max": [],
        }  # fmt: skip
        self.decided: list[tuple[str, str]] = []

    def seen(self, user_id: str) -> None:
        self.users.append(user_id)

    async def persona_rows(self, _pool, user_id):
        self.seen(user_id)
        return []

    async def all_of(self, _pool, user_id):
        self.seen(user_id)
        return list(self.holdings[user_id])

    async def upsert(self, _pool, user_id, ticker, shares, avg_cost, note):
        self.seen(user_id)
        row = {"ticker": ticker.upper(), "shares": shares, "avg_cost": avg_cost, "note": note,
               "updated": "2026-09-16"}  # fmt: skip
        self.holdings[user_id].append(row)

    async def remove(self, _pool, user_id, ticker):
        self.seen(user_id)
        before = len(self.holdings[user_id])
        self.holdings[user_id] = [h for h in self.holdings[user_id] if h["ticker"] != ticker]
        return len(self.holdings[user_id]) < before

    async def search(self, _pool, _embedder, user_id, _query, limit, kinds):
        self.seen(user_id)
        return [m for m in self.memories[user_id] if m["kind"] in kinds][:limit]

    async def by_topic(self, _pool, user_id, _per_topic):
        self.seen(user_id)
        return list(self.memories[user_id])

    async def add(self, _pool, _embedder, user_id, topic, content):
        self.seen(user_id)
        memory_id = f"mem-{user_id}-{len(self.memories[user_id]) + 1}"
        memory = {"id": memory_id, "kind": "memory", "topic": topic, "key": None,
                  "content": content, "created": "2026-09-16"}  # fmt: skip
        self.memories[user_id].append(memory)
        return {"id": memory["id"], "deduped": False}

    async def delete(self, _pool, user_id, memory_id):
        self.seen(user_id)
        before = len(self.memories[user_id])
        self.memories[user_id] = [m for m in self.memories[user_id] if m["id"] != memory_id]
        return len(self.memories[user_id]) < before

    async def latest(self, _pool, user_id, ticker):
        self.seen(user_id)
        found = [t for t in self.theses[user_id] if t["ticker"] == ticker.upper()]
        return found[-1] if found else None

    async def recent(self, _pool, user_id, _limit):
        self.seen(user_id)
        return [{"ticker": t["ticker"], "created": t["created"], "action": t["advice"]["action"],
                 "verdict": "approve"} for t in self.theses[user_id]]  # fmt: skip

    async def save(self, _pool, user_id, ticker, story, review, advice, revisions):
        self.seen(user_id)
        self.theses[user_id].append({"ticker": ticker, "story": story, "review": review,
                                     "advice": advice, "revisions": revisions,
                                     "created": "2026-09-16"})  # fmt: skip
        return f"thesis-{user_id}"

    async def matching(self, _pool, user_id, short_id):
        self.seen(user_id)
        return [p for p in self.proposals[user_id] if p["id"].startswith(short_id)]

    async def approve(self, _pool, user_id, proposal_id):
        self.seen(user_id)
        self.decided.append((user_id, proposal_id))
        return True

    reject = approve

    def mats_data(self) -> tuple[Any, ...]:
        return self.holdings["mat"], self.memories["mat"], self.theses["mat"], self.proposals["mat"]


@pytest.fixture
def two_users(monkeypatch) -> TwoUsers:
    store = TwoUsers()
    for module, names in [
        (facts, ["persona_rows"]),
        (holdings, ["all_of", "upsert", "remove"]),
        (memories, ["search", "by_topic", "add", "delete"]),
        (theses, ["latest", "recent", "save"]),
        (soul, ["matching", "approve", "reject"]),
    ]:
        for name in names:
            monkeypatch.setattr(module, name, getattr(store, name))

    async def prices(tickers):
        return dict.fromkeys(tickers, 100.0)

    monkeypatch.setattr(market, "prices", prices)
    return store
