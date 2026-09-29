#!/usr/bin/env bash
# Nightly PostgreSQL backup for the Docker Swarm stack. Run on the node that
# hosts the `db` service. Writes a gzipped dump OUTSIDE Docker volumes and keeps
# the last KEEP_DAYS days. Exits non-zero (so cron/monitoring notices) if the
# dump fails or looks empty.
#
#   BACKUP_DIR  where dumps go            (default /var/backups/unitaryx)
#   KEEP_DAYS   retention in days         (default 14)
#   STACK       swarm stack name          (default unitaryx)
#   DB_USER / DB_NAME                     (default unitaryx / unitaryx)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/unitaryx}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STACK="${STACK:-unitaryx}"
DB_USER="${DB_USER:-unitaryx}"
DB_NAME="${DB_NAME:-unitaryx}"

cid="$(docker ps -q -f "name=${STACK}_db" | head -n1)"
if [ -z "$cid" ]; then
    echo "backup: no running container for service ${STACK}_db on this node" >&2
    exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"
out="$BACKUP_DIR/unitaryx_$(date +%Y%m%d_%H%M%S).sql.gz"
tmp="${out}.partial"
trap 'rm -f "$tmp"' EXIT

docker exec "$cid" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges | gzip > "$tmp"
gzip -t "$tmp"
if ! zcat "$tmp" | grep -q 'CREATE TABLE public.users'; then
    echo "backup: dump does not contain the users table; refusing to keep it" >&2
    exit 1
fi

mv "$tmp" "$out"
find "$BACKUP_DIR" -maxdepth 1 -name 'unitaryx_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "backup: wrote $out ($(du -h "$out" | cut -f1))"
