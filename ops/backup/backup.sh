#!/bin/sh
# Nightly pg_dump and AnythingLLM storage tar, run by the compose `backup` service (see
# docker-compose.yaml). Runs once at start (so a deploy proves backups work), then at 03:00 UTC,
# to /backups, and keeps the newest BACKUP_KEEP of each. A failure removes its partial file and
# exits, so compose restarts the container and its healthcheck goes unhealthy once none is recent.
# The tar is taken from the live volume (read-only mount); AnythingLLM writes rarely at 03:00.
set -eu
umask 077

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}" "${BACKUP_KEEP:?}"

partial=""
trap '[ -n "$partial" ] && rm -f -- "$partial"' EXIT

# prune <glob>: keep the newest BACKUP_KEEP files matching it.
prune() {
  ls -1t $1 | tail -n +$((BACKUP_KEEP + 1)) | xargs -r rm --
}

# finish <out>: move the partial file into place and report it.
finish() {
  mv -- "$partial" "$1"
  partial=""
  echo "backup: wrote $1 ($(du -h "$1" | cut -f1))"
}

dump() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  out="/backups/${PGDATABASE}-$stamp.dump"
  partial="$out.partial"
  pg_dump --format=custom --file="$partial"
  finish "$out"
  prune "/backups/${PGDATABASE}-*.dump"

  [ -d /anythingllm ] || { echo "backup: /anythingllm is not mounted" >&2; exit 1; }
  out="/backups/anythingllm-$stamp.tar.gz"
  partial="$out.partial"
  tar -czf "$partial" -C /anythingllm .
  finish "$out"
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
