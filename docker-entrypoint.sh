#!/bin/sh
# Runs as root (the container's default user) before the app starts.
#
# docker-compose.yml bind-mounts host paths over /app/data,
# /app/instance/db_backups and /app/frontend/static/uploads at runtime. That
# mount shadows whatever the Dockerfile chowned to appuser at build time, so
# the ownership the app actually sees is whatever the host/Portainer created
# for the mount (commonly root:root when the host directory didn't already
# exist). Fix it here on every start, then drop to appuser to run the app —
# this makes the app writable regardless of host-side ownership, without
# needing a one-time manual chown on the host.
set -e

for dir in /app/data /app/instance/db_backups /app/frontend/static/uploads; do
    mkdir -p "$dir"
    chown -R appuser:appuser "$dir"
done

exec gosu appuser "$@"
