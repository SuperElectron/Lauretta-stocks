"""Agent process configuration, read from the environment (`just` loads `.env`)."""

from typing import Literal

from pydantic import PositiveInt, model_validator
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
