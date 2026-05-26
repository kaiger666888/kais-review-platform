---
phase: 15-foundation
plan: 02
subsystem: infra
tags: [postgresql, timescaledb, minio, docker, alembic, asyncpg, pydantic-settings]

# Dependency graph
requires:
  - phase: 15-foundation/01
    provides: Shot Card data model, init-db.sql, Alembic setup (created in parallel)
provides:
  - V2 Settings class with postgres_url, minio_endpoint, git_repo_url, capability_token_secret
  - Updated requirements.txt with asyncpg, alembic, gitpython, minio (no aiosqlite)
  - Expanded Docker Compose with PostgreSQL + MinIO (6 services, 768M total)
  - Updated Dockerfile copying alembic files (no SQLite data directory)
  - Updated start.sh running alembic upgrade head
  - .env.example documenting all V2 environment variables
affects: [16-policy-engine, 17-gitops-sync, 18-api-gateway, 22-storage-tiers]

# Tech tracking
tech-stack:
  added: [asyncpg==0.31.0, alembic==1.18.4, gitpython==3.1.50, minio==7.2.20, timescale/timescaledb:latest-pg16, minio/minio:latest]
  patterns: [PostgreSQL async engine via asyncpg, Docker Compose with health-checked dependencies, Alembic migration at startup]

key-files:
  created: [.env.example]
  modified: [app/core/config.py, requirements.txt, docker-compose.yml, Dockerfile, scripts/start.sh]

key-decisions:
  - "PostgreSQL default connection uses service name 'postgres' not localhost (Docker networking)"
  - "Redis URL default updated to redis://redis:6379/0 for Docker networking"
  - "MinIO exposes both API (9000) and Console (9001) ports internally only"
  - "Dockerfile copies alembic.ini and alembic/ directory for migration support"
  - "start.sh runs alembic upgrade head as first step before uvicorn"

patterns-established:
  - "Settings class uses pydantic-settings with env_file=.env and all V2 fields"
  - "Docker Compose healthcheck + depends_on condition:service_healthy for startup ordering"
  - "Memory budget: PostgreSQL 256M + API 256M + MinIO 128M + Redis 64M + Nginx 32M = 768M"

requirements-completed: [DB-04, AUTH-02, AUTH-03]

# Metrics
duration: 2min
completed: 2026-05-16
---

# Phase 15 Plan 02: V2 Infrastructure Summary

**Docker Compose expansion with PostgreSQL + TimescaleDB and MinIO, V2 Settings with postgres_url/minio_endpoint/git_repo_url, updated requirements swapping aiosqlite for asyncpg**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-16T07:32:11Z
- **Completed:** 2026-05-16T07:34:11Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Rewrote Settings class replacing database_url with postgres_url and adding MinIO, Git, retention, and capability token fields
- Expanded Docker Compose from 4 to 6 services (added PostgreSQL with TimescaleDB and MinIO), total memory 768M under 1GB budget
- Updated requirements.txt: added asyncpg, alembic, gitpython, minio; removed aiosqlite
- Updated Dockerfile to copy alembic migration files, removed SQLite data directory setup
- Updated start.sh to run alembic upgrade head before uvicorn
- Created comprehensive .env.example with all V2 environment variables

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite Settings class and update requirements.txt** - `3d9528a` (feat)
2. **Task 2: Expand Docker Compose and update Dockerfile + start.sh** - `e2b826f` (feat)

## Files Created/Modified
- `app/core/config.py` - V2 Settings class with postgres_url, minio_endpoint, git_repo_url, capability_token_secret
- `requirements.txt` - V2 dependencies: asyncpg, alembic, gitpython, minio added; aiosqlite removed
- `.env.example` - All V2 environment variables documented with comments
- `docker-compose.yml` - 6-service compose with PostgreSQL (TimescaleDB) and MinIO
- `Dockerfile` - Copies alembic files, no SQLite data directory
- `scripts/start.sh` - Runs alembic upgrade head before application startup

## Decisions Made
- PostgreSQL default URL uses Docker service name `postgres` not `localhost` (matches Docker Compose networking)
- Redis URL default updated from `redis://localhost:6379/0` to `redis://redis:6379/0` for Docker networking
- MinIO exposes both API port 9000 and Console port 9001, internal only (no host port mapping)
- API container uses `env_file: .env.production` for production config (existing pattern)
- init-db.sql mounted directly into PostgreSQL container via docker-entrypoint-initdb.d (not copied into API image)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- V2 infrastructure layer complete: Docker Compose, config, dependencies, startup script all updated
- PostgreSQL and MinIO containers configured and ready for Plan 01's init-db.sql and Alembic migrations
- Settings class has all fields needed by downstream phases (policy engine, GitOps sync, storage tiers)
- Docker memory budget at 768M of 1GB, 256M headroom for burst usage

## Self-Check: PASSED

All files verified present:
- app/core/config.py, requirements.txt, .env.example, docker-compose.yml, Dockerfile, scripts/start.sh
- .planning/phases/15-foundation/15-02-SUMMARY.md

All commits verified:
- 3d9528a (Task 1: Settings + requirements)
- e2b826f (Task 2: Docker Compose + Dockerfile + start.sh)

---
*Phase: 15-foundation*
*Completed: 2026-05-16*
