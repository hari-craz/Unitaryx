#!/bin/sh
# Runs as root (the container's default user) before the app starts.
#
# 1. Fix volume permissions for /app/data, /app/instance/db_backups, and
#    /app/frontend/static/uploads before dropping privileges.
# 2. In Swarm/orchestrated setups where services start concurrently, wait
#    briefly for PostgreSQL and Redis to be reachable before launching Gunicorn
#    or Celery, avoiding premature crashes on cold boot.
set -e

for dir in /app/data /app/instance/db_backups /app/frontend/static/uploads; do
    mkdir -p "$dir"
    chown -R appuser:appuser "$dir"
done

# Wait for PostgreSQL if DB_HOST is configured and external
if [ -n "$DB_HOST" ] && [ "$DB_HOST" != "localhost" ] && [ "$DB_HOST" != "127.0.0.1" ]; then
    echo "[entrypoint] Verifying database connectivity at ${DB_HOST}:${DB_PORT:-5432}..."
    python3 - <<'EOF'
import os
import socket
import sys
import time

host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", 5432))
timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", 60))
deadline = time.time() + timeout

connected = False
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] Database connection established at {host}:{port}")
            connected = True
            break
    except Exception:
        time.sleep(1)

if not connected:
    print(f"[entrypoint] ERROR: Timed out waiting for database at {host}:{port} after {timeout}s", file=sys.stderr)
    sys.exit(1)
EOF
fi

# Wait for Redis if configured and external
_redis_target=""
if [ -n "$REDIS_HOST" ] && [ "$REDIS_HOST" != "localhost" ] && [ "$REDIS_HOST" != "127.0.0.1" ]; then
    _redis_target="$REDIS_HOST"
elif [ -n "$CELERY_BROKER_URL" ] && [ "$CELERY_BROKER_URL" != "memory://" ]; then
    _redis_target="check"
fi

if [ -n "$_redis_target" ]; then
    echo "[entrypoint] Verifying Redis connectivity..."
    python3 - <<'EOF'
import os
import socket
import sys
import time
import urllib.parse

broker = os.environ.get("CELERY_BROKER_URL", "")
host = os.environ.get("REDIS_HOST", "")
port = int(os.environ.get("REDIS_PORT", 6379))

if broker.startswith("redis://"):
    parsed = urllib.parse.urlparse(broker)
    host = parsed.hostname or host or "redis"
    port = parsed.port or port

if host and host not in ("localhost", "127.0.0.1"):
    timeout = int(os.environ.get("REDIS_CONNECT_TIMEOUT", 45))
    deadline = time.time() + timeout
    connected = False
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[entrypoint] Redis connection established at {host}:{port}")
                connected = True
                break
        except Exception:
            time.sleep(1)
    if not connected:
        print(f"[entrypoint] WARNING: Redis at {host}:{port} was not reachable within {timeout}s", file=sys.stderr)
EOF
fi

exec gosu appuser "$@"
