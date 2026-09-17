"""API process configuration, read from the environment (`just` loads `.env`)."""

import re

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# A user id: it prefixes thread keys as `{user}:{thread}`, so it never holds a colon.
USER_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class Settings(BaseSettings):
    # The .env also carries the worker's and the containers' variables.
    model_config = SettingsConfigDict(extra="ignore")
    LOG_LEVEL: str
    # Everyone who may use the desk, comma-separated user ids; the first is the owner. The API
    # acts only for a user named here, as the gateway's `X-Lauretta-User` header.
    ALLOWED_USERS: str
    # The app role (`lauretta_app`), which row-level security applies to.
    DATABASE_URL: str
    DB_POOL_MIN: int
    DB_POOL_MAX: int
    # The job queue (Valkey/Redis Streams).
    BROKER_URL: str | None = None
    # How long a job's status and events are kept for polling and resuming.
    EVENTS_TTL_S: PositiveInt = 86_400
    # The longest `POST /v1/jobs?wait=` may block before answering 202. The gateway's
    # requestTimeout (30s) bounds the time to response headers, so stay under it.
    API_MAX_WAIT_S: PositiveInt = 25
    # An SSE stream ends with a `timeout` event (STREAM_TIMEOUT) after this long; the job goes on.
    API_MAX_STREAM_S: PositiveInt = 900
    # The secret the gateway adds as `X-Lauretta-Gateway` (`api/edge.py`); api refuses anything
    # without it. Unset (tests, local runs) nothing is checked; compose always sets it.
    API_GATEWAY_SECRET: str | None = None
    # Speech (speaches: faster-whisper and Kokoro on CPU), reached by the API only. Unset, the
    # voice routes answer 503.
    SPEECH_URL: str | None = None
    STT_MODEL: str = "Systran/faster-whisper-small"
    TTS_MODEL: str = "speaches-ai/Kokoro-82M-v1.0-ONNX"
    # The Director's voice unless the user's `tts_voice` identity fact names another.
    TTS_VOICE: str = "af_heart"
    VOICE_MAX_UPLOAD_BYTES: PositiveInt = 10_000_000

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
        """BROKER_URL, required by the API."""
        if not self.BROKER_URL:
            raise ValueError("BROKER_URL is required to run the API")
        return self.BROKER_URL
