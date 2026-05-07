# Phase 4 Research: Deployment & Hardening

**Date:** 2026-05-06
**Discovery Level:** 1 (Quick Verification - known stack, confirming configuration patterns)

## Findings

### 1. Current Application Entry Point

- `app/main.py` uses `uvicorn` implicitly (FastAPI app, no `if __name__` block)
- Health endpoint exists at `GET /health` returning `{"status": "ok"}`
- Lifespan handles: SQLite schema creation, Redis connect, arq pool connect, default policy loading
- Database: `sqlite+aiosqlite:///./data/review.db` (relative path from CWD)
- Redis: `redis://localhost:6379/0`
- Config via `pydantic-settings` from `.env` file

### 2. Memory Budget Analysis

| Service | Image | Memory Limit | Estimated Actual |
|---------|-------|-------------|-----------------|
| api | python:3.12-slim | 256M | 80-150M |
| nginx | nginx:alpine | 32M | 8-16M |
| redis | redis:7-alpine | 64M | 20-40M |
| dozzle (optional) | amir20/dozzle:latest | 32M | 8-12M |
| **Total** | | **384M** | **~120-220M** |

Key: python:3.12-slim chosen over alpine because compiled deps (sqlalchemy, cext) need glibc. Total well under 400MB.

### 3. SQLite in Docker - Critical Path

- Already using WAL mode via `set_sqlite_pragma` event listener in `database.py`
- Bind mount `./data:/app/data` for persistence
- MUST ensure data directory exists before container start
- Single-writer constraint: only one api container (no replicas)
- `PRAGMA busy_timeout=5000` already set

### 4. Nginx SSE Configuration

SSE requires specific proxy settings (already documented in DEPLOYMENT-FEASIBILITY.md):
- `proxy_buffering off` - critical for SSE
- `proxy_cache off`
- `proxy_http_version 1.1`
- `proxy_set_header Connection ''`
- `proxy_read_timeout 86400s` - long-lived connections
- `chunked_transfer_encoding off`

SSE endpoint: `/events/stream` (from `app/web/sse.py`)

Rate limiting zones needed:
- API general: 10 req/s
- SSE: no rate limit (long-lived connections)
- Auth endpoints: stricter (5 req/s)

### 5. Security Hardening Pattern

From CLAUDE.md constraints:
- `read_only: true` with tmpfs for /tmp
- `cap_drop: ALL` (with minimal cap_add)
- `security_opt: no-new-privileges:true`
- Non-root user via `user: "1000:1000"` in Dockerfile

API container needs writable `/tmp` (Python temp files) and `/app/data` (SQLite).
Redis cannot be fully read_only (writes to /data for AOF persistence).

### 6. Docker Compose V2 Syntax

- No `version:` key needed (Compose V2 spec)
- `depends_on` with `condition: service_healthy` for startup ordering
- `deploy.resources` for memory/CPU limits
- Health checks with `start_period` for graceful startup

### 7. Application Configuration for Docker

Current `.env` values need adjustment for container networking:
- `REDIS_URL=redis://redis:6379/0` (service name, not localhost)
- `DATABASE_URL=sqlite+aiosqlite:///./data/review.db` (relative path works with bind mount)
- Port 8090 on host mapped to Nginx (per CLAUDE.md: http://192.168.71.140:8090)

### 8. .dockerignore Requirements

Must exclude: `.venv`, `.git`, `.planning`, `__pycache__`, `.env`, `data/`, `tests/`, `*.md` (non-essential docs).

## Standard Stack

- Docker Compose V2 (no version key)
- python:3.12-slim base image
- nginx:alpine for reverse proxy
- redis:7-alpine for cache/queue
- Multi-stage build not needed (Python, no build step)

## Architecture Decisions

1. **Single Dockerfile** in project root (no subdirectory structure needed - app is Python, not Node)
2. **Nginx handles port 8090** externally, proxies to api:8000 internally
3. **Redis named volume** for persistence (AOF enabled)
4. **SQLite bind mount** `./data:/app/data` (easier backup/inspection)
5. **Health check endpoint** already exists at `/health` - extend with Redis/DB checks

## Common Pitfalls

1. **SQLite WAL files**: The `-wal` and `-shm` files must be on the same filesystem as the DB. Bind mount the directory, not the file.
2. **Nginx buffering SSE**: Must explicitly disable all buffering on SSE location.
3. **Redis maxmemory**: Must set `--maxmemory` to prevent Redis from consuming all container memory.
4. **Container DNS**: Use service names (api, redis) not localhost within Docker network.
5. **Non-root + bind mount**: Host directory must be writable by UID 1000 (or match Dockerfile USER).
