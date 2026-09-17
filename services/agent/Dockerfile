# The agent service: the worker (compose `worker`) and the checkpoint migrate (`migrate`). Builds
# natively on linux/arm64 (the Spark) and linux/amd64.

FROM python:3.14.7-slim AS build

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14.7-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH=/cache/fastembed

# The embedding model downloads here on first use; compose mounts a volume over /cache so it
# survives rebuilds. The directory exists and belongs to the app user, so the volume inherits
# that owner when it is first created.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /cache/fastembed \
    && chown -R app:app /cache

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=app:app src ./src
COPY --chown=app:app healthcheck.py ./healthcheck.py

USER app

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD ["python", "/app/healthcheck.py", "worker"]

CMD ["python", "-m", "src.worker"]
