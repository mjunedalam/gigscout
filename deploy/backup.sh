#!/bin/sh
# Backs up GigScout: the Postgres database (pg_dump, custom format) and the API's data volume (lead vector store
# and settings files), into /backups, keeping BACKUP_KEEP_DAYS days.
#   sh /backup.sh            one backup now
#   sh /backup.sh --daily    every day at BACKUP_HOUR_UTC (what the compose service runs)
# Restore: see docs/DEPLOY.md.
set -eu

KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

backup_once() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  mkdir -p /backups
  pg_dump --format=custom --no-owner --file="/backups/db-$stamp.dump.partial"
  mv "/backups/db-$stamp.dump.partial" "/backups/db-$stamp.dump"
  tar -czf "/backups/appdata-$stamp.tar.gz.partial" -C /appdata --exclude=./models .
  mv "/backups/appdata-$stamp.tar.gz.partial" "/backups/appdata-$stamp.tar.gz"
  find /backups -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
  find /backups -name 'appdata-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
  echo "backup $stamp done"
}

if [ "${1:-}" != "--daily" ]; then
  backup_once
  exit 0
fi

hour="${BACKUP_HOUR_UTC:-2}"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) $hour:00:00" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  backup_once || echo "backup failed; will try again tomorrow" >&2
done
