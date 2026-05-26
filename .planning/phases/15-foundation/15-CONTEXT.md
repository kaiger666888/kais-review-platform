# Phase 15: Foundation - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase)

<domain>
## Phase Boundary

The platform runs on PostgreSQL with a complete Shot Card data model, ready for all downstream engine and UI layers. This is the foundational rewrite — replacing SQLite with PostgreSQL, replacing the flat Review model with the nested Shot Card model, expanding Docker Compose, and updating all configuration.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key reference documents:
- `.planning/research/V2-ARCHITECTURE.md` — Shot Card data model YAML structure
- `.planning/research/V2-GAP-ANALYSIS.md` — GAP-2.1 (Shot Card model), GAP-4.1 (PostgreSQL migration)
- Existing V1 codebase patterns in `app/` for SQLAlchemy models, config, Docker setup

### Pre-established Decisions
- PostgreSQL + TimescaleDB replaces SQLite (user confirmed)
- Memory budget relaxed to 1GB (user confirmed)
- asyncpg driver (not psycopg) — async-native, matches FastAPI patterns
- Full rewrite, not incremental migration — V1 code can be replaced entirely
- Shot Card data model per V2 architecture spec (shot_id, project_id, narrative_context, visual_bundle, audio_bundle, audit_state, provenance)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/core/config.py` — Settings class with pydantic-settings, can be extended
- `app/core/database.py` — SQLAlchemy async engine setup, pattern reusable with PostgreSQL
- `app/models/schema.py` — SQLAlchemy model patterns (Review, AuditEntry, PolicyVersion, WebhookConfig)
- `app/models/schemas.py` — Pydantic model patterns
- `docker-compose.yml` — Container orchestration with resource limits, health checks
- `Dockerfile` — Python 3.12-slim base, non-root user, security hardening

### Established Patterns
- SQLAlchemy 2.0 async engine with declarative models
- pydantic-settings for config with `.env` support
- Docker Compose with resource limits and security constraints
- arq task queue on Redis

### Integration Points
- All engine components depend on Shot Card model (Phase 16-22)
- All components depend on PostgreSQL connection (database.py)
- Docker Compose must expose PostgreSQL port for API container

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Follow V2 architecture spec for data model structure.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.
