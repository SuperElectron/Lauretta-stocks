"""Agent process configuration, read from the environment (`just` loads `.env`)."""

import re
from typing import Literal

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# A user id: it prefixes thread keys as `{user}:{thread}`, so it never holds a colon.
USER_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class Settings(BaseSettings):
    # The .env also carries the db container's variables and the provider keys, which the
    # model clients read themselves.
    model_config = SettingsConfigDict(extra="ignore")
    LOG_LEVEL: str
    # Everyone who may use the desk, comma-separated user ids; the first is the owner. The API
    # acts only for a user named here, as the gateway's `X-Lauretta-User` header.
    ALLOWED_USERS: str
    # The app role (`lauretta_app`), which row-level security applies to.
    DATABASE_URL: str
    # `lauretta_migrator`, which owns the checkpoint tables and may create tables but reads no
    # user data. Set for `python -m src.db.migrate` (the compose `migrate` service), or locally so
    # the CLI creates the tables itself; never on the long-running worker, which then only
    # checks that the tables are current.
    DATABASE_SETUP_URL: str | None = None
    DB_POOL_MIN: int
    DB_POOL_MAX: int
    AGENT_PROVIDER: Literal["anthropic", "openai"]
    AGENT_MODEL: str
    AGENT_BASE_URL: str | None = None
    AGENT_TEMPERATURE: float
    AGENT_MAX_TOKENS: PositiveInt
    AGENT_TIMEOUT: float
    AGENT_RECURSION_LIMIT: PositiveInt
    # Stream the assistant model's own reasoning (unverified thinking) to clients.
    AGENT_STREAM_REASONING: bool = True
    PIPELINE_MAX_REVISIONS: int
    # How long a chat turn waits with the investor for the research it started, before leaving
    # the team to finish in the background and reporting it on a later message.
    RESEARCH_FOLLOW_S: PositiveInt = 900
    EMBED_MODEL: str
    EMBED_DIMS: PositiveInt
    SEC_USER_AGENT: str
    # The job queue (Valkey/Redis Streams), used by the worker, never the CLI.
    BROKER_URL: str | None = None
    # A job pending this long belonged to a worker that died, and is taken over.
    BROKER_MIN_IDLE_MS: PositiveInt = 60_000
    # A job delivered this many times without finishing goes to `jobs:dead`.
    BROKER_MAX_DELIVERIES: PositiveInt = 3
    WORKER_CONCURRENCY: PositiveInt = 4
    # How long a chat job waits for another job on its thread before failing THREAD_BUSY.
    AGENT_LOCK_WAIT_MS: PositiveInt = 30_000
    # The thread lock's TTL; the worker refreshes it every third while the job runs.
    AGENT_LOCK_TTL_MS: PositiveInt = 30_000
    # How long a job's status and events are kept for polling and resuming.
    EVENTS_TTL_S: PositiveInt = 86_400

    @model_validator(mode="after")
    def _sec_user_agent_names_a_contact(self) -> "Settings":
        if "@" not in self.SEC_USER_AGENT:
            raise ValueError(
                'SEC_USER_AGENT must name you and an email, for example "Jo Bloggs jo@example.com"'
            )
        return self

    @model_validator(mode="after")
    def _openai_needs_base_url(self) -> "Settings":
        if self.AGENT_PROVIDER == "openai" and not self.AGENT_BASE_URL:
            raise ValueError("AGENT_BASE_URL is required when AGENT_PROVIDER=openai")
        return self

    @model_validator(mode="after")
    def _lock_wait_ends_before_reclaim(self) -> "Settings":
        # A job still waiting for its thread must not look abandoned to other workers.
        if self.AGENT_LOCK_WAIT_MS >= self.BROKER_MIN_IDLE_MS:
            raise ValueError("AGENT_LOCK_WAIT_MS must be less than BROKER_MIN_IDLE_MS")
        return self

    @model_validator(mode="after")
    def _allowed_users_are_ids(self) -> "Settings":
        users = self.allowed_users()
        if not users or any(USER_ID.fullmatch(user) is None for user in users):
            raise ValueError("ALLOWED_USERS must list user ids like mat,max (a-z, 0-9, _ or -)")
        return self

    def allowed_users(self) -> tuple[str, ...]:
        """The user ids in ALLOWED_USERS, owner first."""
        return tuple(user.strip() for user in self.ALLOWED_USERS.split(",") if user.strip())

    def owner(self) -> str:
        return self.allowed_users()[0]

    def broker_url(self) -> str:
        """BROKER_URL, required by the worker."""
        if not self.BROKER_URL:
            raise ValueError("BROKER_URL is required to run the worker")
        return self.BROKER_URL
