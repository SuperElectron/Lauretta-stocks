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

# docker: start the database.
up:
    docker compose up -d --wait db

# docker: stop (add clean=true to wipe memories, holdings and theses).
down clean="false":
    docker compose down {{ if clean == "true" { "-v" } else { "" } }}

# test: unit tests and lint.
test:
    cd agent && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
