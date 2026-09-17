"""Test helpers: valid settings without the environment."""

from typing import Any


def settings(**overrides: Any) -> Any:
    """A valid `Settings` without the environment; overrides replace any field."""
    from src.settings import Settings

    values: dict[str, Any] = {
        "LOG_LEVEL": "INFO",
        "ALLOWED_USERS": "mat,max",
        "DATABASE_URL": "postgresql://unused",
        "DB_POOL_MIN": 1,
        "DB_POOL_MAX": 2,
        "BROKER_URL": "redis://unused",
        **overrides,
    }
    return Settings(**values)
