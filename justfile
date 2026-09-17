set dotenv-load := true

# List the available recipes.
help:
    @just --list

# Chat with the assistant; thread="main" continues that conversation.
chat thread="main":
    cd agent && uv run python -m src.main chat --thread {{ thread }}

# Run the research team on one ticker and save a report in reports/.
research ticker:
    cd agent && uv run python -m src.main research {{ ticker }}

# Run the HTTP API on :8000 (needs a broker: `just broker`, and BROKER_URL in .env).
api:
    cd agent && uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000

# Run the job worker that the API queues chat turns and research runs for.
worker:
    cd agent && uv run python -m src.worker

# docker: a throwaway local Valkey on :18479 for `just api` and `just worker` (ctrl-c stops it).
broker:
    docker run --rm -p 127.0.0.1:18479:6379 valkey/valkey:9.0.6-alpine

# Check streaming through the API: time to first token and gaps between tokens.
stream-check:
    cd agent && uv run python scripts/stream_check.py

# docker: start the database.
up:
    docker compose up -d --wait db

# docker: stop (add clean=true to wipe memories, holdings and theses).
down clean="false":
    docker compose down {{ if clean == "true" { "-v" } else { "" } }}

# test: unit tests and lint.
test:
    cd agent && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
