set dotenv-load := true

# Where the stack lives on the Spark (a git clone of this repo, with its own .env).
spark_dir := "~/lauretta-stocks"

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

# docker: start the local database (loopback DB_PORT) for chat and research on this machine.
up:
    docker compose -f docker-compose.dev.yaml up -d --wait db

# docker: stop (add clean=true to wipe memories, holdings and theses).
down clean="false":
    docker compose -f docker-compose.dev.yaml down --remove-orphans {{ if clean == "true" { "-v" } else { "" } }}

# test: unit tests and lint.
test:
    cd agent && uv run pytest -q && uv run ruff check . && uv run ruff format --check .

# spark: pull ref (pushed first) on the Spark, then build natively and start the stack.
deploy ref="main":
    just _spark "cd {{ spark_dir }} && git fetch origin && git checkout {{ quote(ref) }} && git pull --ff-only origin {{ quote(ref) }} && docker compose up -d --build --wait"

# spark: follow the stack's logs, or one service's.
logs service="":
    just _spark "cd {{ spark_dir }} && docker compose logs -f --tail 200 {{ if service == '' { '' } else { quote(service) } }}"

# spark: list the stack's containers and their health.
ps:
    just _spark "cd {{ spark_dir }} && docker compose ps"

# spark: dump the database now into backups/ on the Spark (the backup service also does it nightly).
backup:
    just _spark "cd {{ spark_dir }} && mkdir -p backups && f=backups/manual-\$(date -u +%Y%m%dT%H%M%SZ).dump && docker compose exec -T db sh -c 'pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --format=custom' > \$f.partial && mv \$f.partial \$f"

# Run a command on the Spark over ssh with key auth (BatchMode: never a password prompt).
# Host and user come from .claude/secrets/devices.json; only those two keys are read.
_spark cmd:
    #!/usr/bin/env bash
    set -euo pipefail
    target=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))["spark"]; print(d["username"] + "@" + d["host"])' "{{ justfile_directory() }}/.claude/secrets/devices.json")
    ssh -t -o BatchMode=yes "$target" {{ quote(cmd) }}
