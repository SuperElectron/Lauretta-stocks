set dotenv-load := true

# Where the stack lives on the Spark (a git clone of this repo, with its own .env).
spark_dir := "~/lauretta-stocks"

# List the available recipes.
help:
    @just --list

# Chat with the assistant as user (default: the owner); thread="main" continues that conversation.
chat thread="main" user="":
    cd services/agent && uv run python -m src.main {{ if user == "" { "" } else { "--user " + quote(user) } }} chat --thread {{ thread }}

# Run the research team on one ticker for user (default: the owner) and print its report.
research ticker user="":
    cd services/agent && uv run python -m src.main {{ if user == "" { "" } else { "--user " + quote(user) } }} research {{ ticker }}

# Run the HTTP API on :8000 (needs a broker: `just broker`, and BROKER_URL in .env).
api:
    cd services/api && uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000

# Run the job worker that the API queues chat turns and research runs for.
worker:
    cd services/agent && uv run python -m src.worker

# docker: a throwaway local Valkey on :18479 for `just api` and `just worker` (ctrl-c stops it).
broker:
    docker run --rm -p 127.0.0.1:18479:6379 valkey/valkey:9.0.6-alpine

# Check streaming through the API: time to first token and gaps between tokens.
stream-check *args:
    cd services/api && uv run python scripts/stream_check.py {{ args }}

# Create or migrate the checkpoint tables in the local database (as DATABASE_SETUP_URL, else
# DATABASE_URL). The Spark uses the compose `migrate` service instead.
migrate:
    cd services/agent && uv run python -m src.db.migrate

# docker: start the local database (loopback DB_PORT) for chat and research on this machine.
up: _local-only
    docker compose -f docker-compose.dev.yaml up -d --wait db

# docker: stop the local db (add clean=true to wipe memories, holdings and theses). Local only:
# the dev file shares the stack's project, `db` and `pgdata`, so both recipes refuse on a host
# running the stack (clean=true there would delete every user's data).
down clean="false": _local-only
    docker compose -f docker-compose.dev.yaml down {{ if clean == "true" { "-v" } else { "" } }}

# test: unit tests and lint.
test:
    cd services/api && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
    cd services/agent && uv run pytest -q && uv run ruff check . && uv run ruff format --check .

# test: the database isolation tests (row-level security as the app role) in a throwaway
# compose project; needs docker, removes the project after. Run it on the Spark.
test-db:
    docker compose -f docker-compose.test.yaml run --rm --build tests; status=$?; docker compose -f docker-compose.test.yaml down -v --remove-orphans; exit $status

# spark: pull ref (pushed first) on the Spark, then build natively, migrate the checkpoint tables
# (the one-shot `migrate` service) and start the stack.
# Refuses while the hand-started vllm-gpt-oss-120b runs: two engines do not fit in the Spark's
# memory, so stop and remove it first. Creating or recreating vllm waits about 9 minutes for it.
deploy ref="main":
    just _spark "if docker ps -q --filter name=^vllm-gpt-oss-120b\$ | grep -q .; then echo 'vllm-gpt-oss-120b is running; stop and remove it before deploying (docker stop vllm-gpt-oss-120b && docker rm vllm-gpt-oss-120b)' >&2; exit 1; fi && cd {{ spark_dir }} && git fetch origin && git checkout {{ quote(ref) }} && git pull --ff-only origin {{ quote(ref) }} && docker compose build api worker migrate && docker compose run --rm migrate && docker compose up -d --wait --wait-timeout 1200"

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

# Refuses where the full stack runs or has run: its api container, or a volume only the stack
# creates, exists. up/down would act on its database (clean=true would delete every user's data).
_local-only:
    @if docker ps -a --format '{{{{.Names}}' | grep -qx 'lauretta-stocks-api-1' || docker volume ls -q | grep -qxE 'lauretta-stocks_(anythingllm|tsstate|brokerdata|speechmodels)'; then echo "this host runs the stack; use just deploy/ps/logs instead" >&2; exit 1; fi
