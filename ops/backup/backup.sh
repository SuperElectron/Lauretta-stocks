#!/bin/sh
# Nightly pg_dump, run by the compose `backup` service (see docker-compose.yaml).
# Dumps once at start (so a deploy proves backups work), then at 03:00 UTC, to /backups, and
# keeps the newest BACKUP_KEEP dumps. A failed dump removes its partial file and exits, so
# compose restarts the container and its healthcheck goes unhealthy once no dump is recent.
set -eu
umask 077

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}" "${BACKUP_KEEP:?}"

partial=""
trap '[ -n "$partial" ] && rm -f -- "$partial"' EXIT

dump() {
  out="/backups/${PGDATABASE}-$(date -u +%Y%m%dT%H%M%SZ).dump"
  partial="$out.partial"
  pg_dump --format=custom --file="$partial"
  mv -- "$partial" "$out"
  partial=""
  echo "backup: wrote $out ($(du -h "$out" | cut -f1))"
  ls -1t /backups/"${PGDATABASE}"-*.dump | tail -n +$((BACKUP_KEEP + 1)) | xargs -r rm --
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
