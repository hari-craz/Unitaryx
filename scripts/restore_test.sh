#!/usr/bin/env bash
# Proves a backup is restorable WITHOUT touching production: restores the dump
# into a throwaway Postgres container (no published ports) and prints row counts.
#
#   scripts/restore_test.sh [dump.sql.gz]     (default: newest in BACKUP_DIR)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/unitaryx}"
dump="${1:-$(ls -1t "$BACKUP_DIR"/unitaryx_*.sql.gz 2>/dev/null | head -n1)}"
[ -n "${dump:-}" ] && [ -f "$dump" ] || { echo "restore_test: no dump found" >&2; exit 1; }

name="unitaryx_restore_test_$$"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT

docker run -d --name "$name" -e POSTGRES_USER=unitaryx -e POSTGRES_DB=unitaryx \
    -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine >/dev/null

for _ in $(seq 1 30); do
    docker exec "$name" pg_isready -U unitaryx -d unitaryx >/dev/null 2>&1 && break
    sleep 1
done

zcat "$dump" | docker exec -i "$name" psql -U unitaryx -d unitaryx -v ON_ERROR_STOP=1 -q >/dev/null
echo "restore_test: restored $dump; row counts:"
docker exec "$name" psql -U unitaryx -d unitaryx -tA -c \
    "SELECT 'users', count(*) FROM users UNION ALL SELECT 'projects', count(*) FROM projects UNION ALL SELECT 'founders', count(*) FROM founders;"
echo "restore_test: OK"
