#!/bin/bash
set -e

# Run database migrations (PostgreSQL must be ready -- ensured by docker-compose healthcheck)
alembic upgrade head

exec "$@"
