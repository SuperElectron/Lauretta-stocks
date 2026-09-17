"""Agent process configuration, read from the environment (`just` loads `.env`)."""

from typing import Literal

from pydantic import PositiveFloat, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The .env also carries the db container's variables and the provider keys, which the
    # model clients read themselves.
    model_config = SettingsConfigDict(extra="ignore")
    LOG_LEVEL: str
    USER_ID: str
    DATABASE_URL: str
    DB_POOL_MIN: int
    DB_POOL_MAX: int
    AGENT_PROVIDER: Literal["anthropic", "openai"]
    AGENT_MODEL: str
    AGENT_BASE_URL: str | None = None
    AGENT_TEMPERATURE: float
    AGENT_MAX_TOKENS: PositiveInt
    AGENT_TIMEOUT: float
    AGENT_RECURSION_LIMIT: PositiveInt
    PIPELINE_MAX_REVISIONS: int
    EMBED_MODEL: str
    EMBED_DIMS: PositiveInt
    SEC_USER_AGENT: str
    # The job queue (Valkey/Redis Streams), used by the API and the worker, never the CLI.
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
    CALLBACK_TIMEOUT_S: PositiveFloat = 10.0
    # The longest `POST /v1/jobs?wait=` may block before answering 202.
    API_MAX_WAIT_S: PositiveInt = 300

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

    def broker_url(self) -> str:
        """BROKER_URL, required by the API and the worker."""
        if not self.BROKER_URL:
            raise ValueError("BROKER_URL is required to run the API or the worker")
        return self.BROKER_URL
