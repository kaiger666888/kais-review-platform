#!/bin/bash
set -e

# Run database migrations (PostgreSQL must be ready -- ensured by docker-compose healthcheck)
PYTHONPATH=/app alembic upgrade head || echo "[warn] alembic migration skipped"

exec "$@"
