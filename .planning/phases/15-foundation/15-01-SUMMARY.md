---
phase: 15-foundation
plan: 01
subsystem: database
tags: [postgresql, timescaledb, sqlalchemy, alembic, jsonb, asyncpg, pydantic]

# Dependency graph
requires:
  - phase: none
    provides: "First plan in V2 -- greenfield"
provides:
  - "ShotCard SQLAlchemy model with JSONB columns, ENUM types, GIN indexes"
  - "AuditEntry SQLAlchemy model with composite PK for TimescaleDB hypertable"
  - "Full Pydantic model hierarchy for Shot Card validation"
  - "PostgreSQL async engine with connection pooling"
  - "Alembic async migration setup for V2 schema"
  - "TimescaleDB init SQL with hypertable, compression, retention, immutability trigger"
affects: [16-aggregation, 17-gitops, 18-routing, 19-ai-tokens, 20-desktop-ui, 21-mobile-ui, 22-audit-data]

# Tech tracking
tech-stack:
  added: [asyncpg==0.31.0, alembic==1.18.4]
  patterns: [JSONB columns for nested Shot Card structures, PostgreSQL ENUM types for status safety, TimescaleDB hypertable for time-series audit data, GIN indexes for JSONB query performance, composite PK (created_at, id) for hypertable compatibility, Alembic async migration with NullPool]

key-files:
  created:
    - app/models/base.py
    - app/models/shot_card.py
    - app/models/audit_entry.py
    - alembic.ini
    - alembic/env.py
    - alembic/script.py.mako
    - alembic/versions/001_initial_v2_schema.py
    - scripts/init-db.sql
  modified:
    - app/models/schemas.py
    - app/models/__init__.py
    - app/core/database.py
    - app/core/config.py
    - requirements.txt

key-decisions:
  - "Used JSONB columns for nested Shot Card bundles (narrative_context, visual_bundle, audio_bundle) rather than normalized tables -- data always read/written as unit"
  - "PostgreSQL ENUM types for stable status fields (audit_status, routing_decision) for type safety at DB level"
  - "Composite PK (created_at, id) on audit_entries with created_at first for TimescaleDB partition alignment"
  - "GIN indexes on narrative_context and visual_bundle for JSONB nested query support"
  - "Audit immutability via PostgreSQL BEFORE UPDATE/DELETE trigger rather than SQLite authorizer"
  - "Added postgres_url to config.py (Plan 02 will do full config rewrite)"

patterns-established:
  - "JSONB + GIN index pattern for nested semi-structured data in PostgreSQL"
  - "Alembic async migration runner with asyncio.run() + run_sync() + NullPool"
  - "Pydantic model hierarchy matching JSONB structure for API-layer validation"
  - "PostgreSQL ENUM as SQLAlchemy Enum with explicit name= for Alembic compatibility"

requirements-completed: [SHOT-01, DB-01]

# Metrics
duration: 5min
completed: 2026-05-16
---

# Phase 15 Plan 01: V2 Shot Card Data Model Summary

**SQLAlchemy ShotCard model with JSONB columns, PostgreSQL ENUMs, GIN indexes; AuditEntry with TimescaleDB hypertable composite PK; async Alembic migration; Pydantic validation hierarchy**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-16T07:31:18Z
- **Completed:** 2026-05-16T07:36:56Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Complete V2 data model replacing V1 flat Review entity with nested Shot Card structure
- PostgreSQL-native database layer with asyncpg driver, zero SQLite code in database.py
- TimescaleDB hypertable configuration with compression, retention, and immutability trigger
- Full Alembic migration setup producing the V2 schema from an empty PostgreSQL database

## Task Commits

Each task was committed atomically:

1. **Task 1: Create V2 SQLAlchemy models and Pydantic schemas** - `b4815fd` (feat)
2. **Task 2: Create PostgreSQL database.py, Alembic setup, and TimescaleDB init SQL** - `262a9fd` (feat)

## Files Created/Modified
- `app/models/base.py` - DeclarativeBase for V2 SQLAlchemy models
- `app/models/shot_card.py` - ShotCard model with JSONB, ENUMs, GIN indexes; AuditStatus/RoutingDecision enums
- `app/models/audit_entry.py` - AuditEntry model with composite PK (created_at, id) for TimescaleDB
- `app/models/schemas.py` - Full Pydantic hierarchy: Keyframe, Keyframes, VideoClip, Candidate, VisualBundle, AudioBundle, NarrativeContext, AuditStatePydantic, Provenance, ShotCardCreate/Response
- `app/models/__init__.py` - Updated exports for V2 models
- `app/core/database.py` - PostgreSQL async engine with connection pooling, no SQLite code
- `app/core/config.py` - Added postgres_url field, made api_key/jwt_secret optional for dev
- `alembic.ini` - Alembic configuration with empty sqlalchemy.url (overridden in env.py)
- `alembic/env.py` - Async migration runner with asyncio.run() + run_sync()
- `alembic/script.py.mako` - Standard Alembic migration template
- `alembic/versions/001_initial_v2_schema.py` - Initial V2 schema migration (shot_cards + audit_entries)
- `scripts/init-db.sql` - TimescaleDB extension, hypertable, compression, retention, immutability trigger
- `requirements.txt` - Replaced aiosqlite with asyncpg + alembic

## Decisions Made
- JSONB columns for nested bundles rather than normalized tables -- data always read/written as a unit, structure defined by YAML templates
- PostgreSQL ENUM for stable status fields (4 audit statuses, 4 routing decisions) rather than VARCHAR + CHECK
- Audit immutability via trigger rather than Row-Level Security -- simpler for single-application databases
- Made api_key/jwt_secret optional in config.py with empty string defaults -- Plan 02 will do full config rewrite

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated __init__.py for V2 model imports**
- **Found during:** Task 1 (model import verification)
- **Issue:** __init__.py still imported V1 models (ApproveRequest, ReviewState, etc.) causing ImportError
- **Fix:** Rewrote __init__.py to export V2 models only (ShotCard, AuditEntry, Pydantic schemas)
- **Files modified:** app/models/__init__.py
- **Committed in:** b4815fd (Task 1 commit)

**2. [Rule 3 - Blocking] Added postgres_url and defaults to config.py**
- **Found during:** Task 2 (database.py import verification)
- **Issue:** database.py references settings.postgres_url but config.py only had database_url. Also api_key/jwt_secret were required fields with no .env file, causing ValidationError on import.
- **Fix:** Added postgres_url field, changed api_key/jwt_secret to optional with empty defaults
- **Files modified:** app/core/config.py
- **Committed in:** 262a9fd (Task 2 commit)

**3. [Rule 2 - Missing Critical] Updated requirements.txt to replace aiosqlite**
- **Found during:** Task 2 (completing database layer)
- **Issue:** requirements.txt still had aiosqlite (V1 SQLite driver) and lacked asyncpg + alembic
- **Fix:** Replaced aiosqlite with asyncpg==0.31.0 and alembic==1.18.4 in requirements.txt
- **Files modified:** requirements.txt
- **Committed in:** Part of final metadata commit

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical)
**Impact on plan:** All auto-fixes necessary for imports to work and dependency correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required at this stage. Docker Compose with PostgreSQL will be configured in Plan 02.

## Next Phase Readiness
- ShotCard and AuditEntry models ready for downstream phases (aggregation, policy, routing, UI)
- PostgreSQL async engine and session factory ready for API endpoints
- Alembic migration ready to produce full V2 schema from empty database
- TimescaleDB init SQL ready for Docker entrypoint
- Plan 02 will complete: Docker Compose with PostgreSQL/MinIO containers, full config.py rewrite, Dockerfile update

## Self-Check: PASSED

All 10 plan files verified present. Both task commits (b4815fd, 262a9fd) confirmed in git history.

---
*Phase: 15-foundation*
*Completed: 2026-05-16*
