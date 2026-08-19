# Stage 1: Frontend build (Vite + React public site)
FROM node:22-slim AS frontend-builder

WORKDIR /build

COPY frontend/app/package*.json ./
RUN npm ci

COPY frontend/app/ ./
RUN npm run build


# Stage 2: Builder
FROM python:3.12-slim AS builder

# Set environment variables for build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtualenv or local user directory
COPY requirements-docker.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements-docker.txt


# Stage 3: Final Production Image
FROM python:3.12-slim

# Set runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal runtime dependencies (like curl for healthcheck and postgres client libraries)
# gosu lets the entrypoint start as root (needed to fix mounted-volume
# ownership) and then drop to appuser to actually run the app.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy built wheels from builder stage and install them
COPY --from=builder /usr/src/app/wheels /wheels
COPY --from=builder /app/requirements-docker.txt .
RUN pip install --no-cache /wheels/*

# Create a non-root user 'appuser'
RUN useradd -m -u 1000 appuser

# Copy application code
COPY . /app

# Copy the built React public site (frontend/app/dist) — served by Flask's
# catch-all route (backend/app.py: DIST_DIR)
COPY --from=frontend-builder /build/dist /app/frontend/app/dist

# Setup directories and permissions (best-effort here — these paths are
# bind-mounted at runtime in docker-compose.yml, which shadows this chown;
# docker-entrypoint.sh re-applies it against the actual mounted volume on
# every container start, so ownership is correct regardless of host setup)
RUN mkdir -p /app/data /app/instance/db_backups \
    /app/frontend/static/uploads/founders /app/frontend/static/uploads/projects && \
    chown -R appuser:appuser /app

# Container starts as root so the entrypoint can fix mounted-volume
# ownership, then execs the app as appuser via gosu. Do not add `USER
# appuser` here — it would run before the mount even exists and would be
# overridden by docker-compose.yml's `user:` directive anyway.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 10003

# Healthcheck ensures the app is responsive
HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=40s \
    CMD curl -f http://127.0.0.1:10003/login || exit 1

# Start application using Gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10003", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
