#!/bin/sh
# One-off, for the deploy of per-user isolation (#25): the schema changed, so the database is
# recreated, and the owner's rows are carried over. Run on the Spark from the repo root, with the
# new code checked out and the new .env settings in place (README, Users and isolation):
#
#   sh services/db/reset-and-restore.sh
#
# 1. Builds the new api and worker images (while the old stack still serves).
# 2. Stops api, worker and anythingllm, so nothing writes from here on.
# 3. Dumps the database into backups/ and counts every table's rows. Refuses unless every row
#    belongs to OWNER_USER (default mat).
# 4. Removes the db container and its volume (vllm and the rest keep running), starts db alone on
#    a fresh volume (new schema and roles), and creates the checkpoint tables.
# 5. Restores the rows, one table per pg_restore run (threads before thread_aliases), stopping at
#    the first error, and moves the owner's conversations to their new `{user}:{thread}` keys.
# 6. Checks each table's count against step 3, and only then starts the whole stack.
#
# A failure stops the script with the stack partly down: the dump in backups/ is intact, and
# running the script's steps 4-6 by hand from it is safe. COMPOSE overrides the compose command
# (a throwaway project in tests).
set -eu

C=${COMPOSE:-docker compose}
OWNER_USER=${OWNER_USER:-mat}
TABLES="facts holdings theses threads thread_aliases checkpoints checkpoint_blobs checkpoint_writes"
CHECKPOINTS="checkpoints checkpoint_blobs checkpoint_writes"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="backups/pre-isolation-$stamp.dump"

say() { echo "restore: $*"; }
# Never stop silently: whatever fails, the last line says the script stopped and where the dump is.
trap 'status=$?; [ "$status" -eq 0 ] || echo "restore: stopped (exit $status); the dump, if taken, is $dump" >&2' EXIT
sql() { $C exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At "$@"' _ "$@"; }
counts() {
  for t in $TABLES; do
    if [ "$(sql -c "SELECT to_regclass('public.$t') IS NOT NULL")" = t ]; then
      echo "$t $(sql -c "SELECT count(*) FROM $t")"
    else
      echo "$t absent"
    fi
  done
}

say "building the new api and worker images"
$C build api worker

say "stopping api, worker and anythingllm"
$C stop api worker anythingllm

say "dumping to $dump"
mkdir -p backups
$C exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file=/tmp/pre-isolation.dump'
$C cp db:/tmp/pre-isolation.dump "$dump"
counts > "$dump.counts"
cat "$dump.counts"

others=$(sql -c "SELECT string_agg(DISTINCT user_id, ',') FROM (
    SELECT user_id FROM facts UNION ALL SELECT user_id FROM holdings UNION ALL
    SELECT user_id FROM theses UNION ALL SELECT user_id FROM threads UNION ALL
    SELECT user_id FROM thread_aliases) rows WHERE user_id <> '$OWNER_USER'")
if [ -n "$others" ]; then
  say "rows belong to other users ($others); nothing was changed, start the stack again" >&2
  exit 1
fi

volume=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$($C ps -q db)")
[ -n "$volume" ] || { say "could not find the db volume" >&2; exit 1; }
say "recreating the database (volume $volume)"
$C rm --stop --force db backup
docker volume rm "$volume"
$C up -d --wait db
$C run --rm --no-deps worker python -m src.db.migrate

say "restoring rows"
$C cp "$dump" db:/tmp/pre-isolation.dump
for t in $TABLES; do
  if grep -q "^$t absent$" "$dump.counts"; then
    continue
  fi
  $C exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --data-only --exit-on-error --table="$1" /tmp/pre-isolation.dump' _ "$t"
done
if ! grep -q "^checkpoints absent$" "$dump.counts"; then
  updates=""
  for t in $CHECKPOINTS; do
    updates="$updates UPDATE $t SET thread_id = '$OWNER_USER:' || thread_id;"
  done
  sql -1 -c "$updates"
fi

say "checking counts"
counts > "$dump.restored"
for t in $TABLES; do
  before=$(grep "^$t " "$dump.counts" | cut -d' ' -f2)
  after=$(grep "^$t " "$dump.restored" | cut -d' ' -f2)
  if [ "$before" = absent ]; then
    continue
  fi
  if [ "$before" != "$after" ]; then
    say "$t has $after rows, the dump $before; the stack stays down" >&2
    exit 1
  fi
done
say "every table matches the dump"

say "starting the stack"
$C up -d --wait --wait-timeout 1200
say "done; the dump stays in $dump"
