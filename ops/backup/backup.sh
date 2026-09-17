#!/bin/sh
# Nightly pg_dump and AnythingLLM storage tar, run by the compose `backup` service (see
# docker-compose.yaml). Runs once at start (so a deploy proves backups work), then at 03:00 UTC,
# to /backups. Both files are written before either is kept, and old ones are pruned only after
# both succeed (newest BACKUP_KEEP of each), so a failing run never erodes the history. A failure
# removes its partial files and exits, so compose restarts the container and its healthcheck goes
# unhealthy once none is recent.
#
# The storage is read live (read-only mount). SQLite (anythingllm.db) is copied on its own until
# its mtime holds still across the copy; the re-downloadable models/ and tmp/ are left out; and a
# tar that saw a file change while reading it (exit 1) is retried.
set -eu
umask 077

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}" "${BACKUP_KEEP:?}"

DB_TRIES=10   # SQLite copies, 2 s apart
TAR_TRIES=3   # tars, 5 s apart
SNAP=/tmp/anythingllm-snap
partials=""
trap 'for p in $partials; do rm -f -- "$p"; done; rm -rf -- "$SNAP"' EXIT

# prune <glob>: keep the newest BACKUP_KEEP files matching it.
prune() {
  ls -1t $1 | tail -n +$((BACKUP_KEEP + 1)) | xargs -r rm --
}

# copy_db: copy anythingllm.db into SNAP, retrying while it changes under the copy.
copy_db() {
  n=1
  while :; do
    before=$(stat -c %.9Y.%s /anythingllm/anythingllm.db)
    cp -p -- /anythingllm/anythingllm.db "$SNAP/anythingllm.db"
    [ "$(stat -c %.9Y.%s /anythingllm/anythingllm.db)" = "$before" ] && return 0
    [ "$n" -ge "$DB_TRIES" ] && { echo "backup: anythingllm.db kept changing ($n copies)" >&2; exit 1; }
    echo "backup: anythingllm.db changed during copy $n, retrying" >&2
    n=$((n + 1))
    sleep 2
  done
}

# tar_storage <file>: tar the storage (with the SQLite copy), retrying exit 1 (file changed).
tar_storage() {
  n=1
  while :; do
    rc=0
    tar -czf "$1" --anchored --exclude=./models --exclude=./tmp \
      --exclude=./anythingllm.db --exclude='./anythingllm.db-*' \
      -C /anythingllm . -C "$SNAP" anythingllm.db || rc=$?
    [ "$rc" -eq 0 ] && return 0
    [ "$rc" -ne 1 ] && { echo "backup: tar failed ($rc)" >&2; exit 1; }
    [ "$n" -ge "$TAR_TRIES" ] && { echo "backup: storage kept changing ($n tars)" >&2; exit 1; }
    echo "backup: storage changed during tar $n, retrying" >&2
    n=$((n + 1))
    sleep 5
  done
}

dump() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  db="/backups/${PGDATABASE}-$stamp.dump"
  storage="/backups/anythingllm-$stamp.tar.gz"
  partials="$db.partial $storage.partial"

  pg_dump --format=custom --file="$db.partial"

  [ -f /anythingllm/anythingllm.db ] || { echo "backup: /anythingllm has no anythingllm.db" >&2; exit 1; }
  rm -rf -- "$SNAP" && mkdir -p -- "$SNAP"
  copy_db
  tar_storage "$storage.partial"
  rm -rf -- "$SNAP"

  mv -- "$db.partial" "$db"
  mv -- "$storage.partial" "$storage"
  partials=""
  echo "backup: wrote $db ($(du -h "$db" | cut -f1)) and $storage ($(du -h "$storage" | cut -f1))"
  prune "/backups/${PGDATABASE}-*.dump"
  prune "/backups/anythingllm-*.tar.gz"
}

dump
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "tomorrow 03:00" +%s)
  today=$(date -u -d "today 03:00" +%s)
  [ "$today" -gt "$now" ] && next=$today
  echo "backup: next dump at $(date -u -d "@$next" +%FT%TZ)"
  sleep $((next - now))
  dump
done
