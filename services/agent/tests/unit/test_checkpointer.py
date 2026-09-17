"""The worker and the CLI start only on current checkpoint tables, and say how to create them."""

from contextlib import asynccontextmanager

import pytest

from src.db import checkpointer
from src.db.checkpointer import CHECKPOINTS_NOT_MIGRATED
from src.errors import DatabaseUnavailable


class Pool:
    """A pool whose one query answers `version`, or fails like a missing table."""

    def __init__(self, version=None, fails=False) -> None:
        self.version, self.fails = version, fails

    @asynccontextmanager
    async def connection(self):
        yield self

    async def execute(self, _sql):
        if self.fails:
            raise RuntimeError("relation checkpoint_migrations does not exist")
        return self

    async def fetchone(self):
        return {"v": self.version}


LATEST = len(checkpointer.AsyncPostgresSaver.MIGRATIONS) - 1


@pytest.mark.parametrize("pool", [Pool(fails=True), Pool(version=None), Pool(version=LATEST - 1)])
async def test_missing_or_stale_tables_stop_with_both_ways_to_create_them(pool):
    with pytest.raises(DatabaseUnavailable) as raised:
        await checkpointer.build_checkpointer(pool)
    assert raised.value.message == CHECKPOINTS_NOT_MIGRATED
    assert "just migrate" in raised.value.message and "DATABASE_SETUP_URL" in raised.value.message


async def test_current_tables_need_no_setup_url():
    assert await checkpointer.build_checkpointer(Pool(version=LATEST)) is not None
