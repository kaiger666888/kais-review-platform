#!/bin/bash
set -e

mkdir -p /app/data
chmod 777 /app/data 2>/dev/null || true

exec "$@"
