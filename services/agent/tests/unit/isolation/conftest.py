"""Isolation tests' fixtures: a fake broker and two investors' data behind the query functions
(`two_users.py`)."""

import pytest
from fakeredis import FakeAsyncRedis

from tests.unit.isolation.two_users import two_users  # noqa: F401


@pytest.fixture
def broker():
    return FakeAsyncRedis(decode_responses=True)
