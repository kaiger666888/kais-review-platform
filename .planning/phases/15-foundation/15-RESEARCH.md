# Phase 15: Foundation - Research

**Researched:** 2026-05-16
**Domain:** PostgreSQL migration, SQLAlchemy 2.0 async, TimescaleDB, Docker Compose, Shot Card data model
**Confidence:** HIGH

## Summary

Phase 15 replaces the SQLite foundation with PostgreSQL + TimescaleDB, introduces the Shot Card data model as the new core entity, expands Docker Compose with PostgreSQL and MinIO containers, and updates all configuration and dependencies. This is a foundational rewrite -- V1 code can be replaced entirely.

The core technical challenge is migrating from `sqlite+aiosqlite` to `postgresql+asyncpg` with SQLAlchemy 2.0 async, which requires: (1) removing all SQLite-specific PRAGMAs and the SQLite authorizer, (2) introducing PostgreSQL-native features (JSONB columns, ENUM types, GIN indexes), (3) setting up TimescaleDB hypertables for audit_entries, (4) configuring Alembic for async PostgreSQL migrations, and (5) rebalancing Docker Compose memory allocation to fit within 1GB total.

The Shot Card data model uses JSONB columns for nested structures (narrative_context, visual_bundle, audio_bundle) rather than separate tables, because: the data is always read/written as a unit, the structure is defined by YAML templates (not relational integrity), and JSONB with GIN indexes provides sufficient query performance for this workload. PostgreSQL ENUMs handle status fields (audit_status, routing_decision, audio_status) for type safety.

**Primary recommendation:** Use a single `shot_cards` table with JSONB columns for nested bundles, TimescaleDB hypertable for `audit_entries`, Alembic for schema migrations, and strict 1GB Docker memory budget (PostgreSQL 256M + API 256M + Redis 64M + MinIO 128M + Nginx 32M + headroom).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- PostgreSQL + TimescaleDB replaces SQLite (user confirmed)
- Memory budget relaxed to 1GB (user confirmed)
- asyncpg driver (not psycopg) -- async-native, matches FastAPI patterns
- Full rewrite, not incremental migration -- V1 code can be replaced entirely
- Shot Card data model per V2 architecture spec (shot_id, project_id, narrative_context, visual_bundle, audio_bundle, audit_state, provenance)

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key reference documents:
- `.planning/research/V2-ARCHITECTURE.md` -- Shot Card data model YAML structure
- `.planning/research/V2-GAP-ANALYSIS.md` -- GAP-2.1 (Shot Card model), GAP-4.1 (PostgreSQL migration)
- Existing V1 codebase patterns in `app/` for SQLAlchemy models, config, Docker setup

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SHOT-01 | Shot Card data model: shot_id, project_id, narrative_context, visual_bundle, audio_bundle, audit_state, provenance | JSONB column pattern with SQLAlchemy 2.0 `mapped_column`, GIN indexes for nested queries, Pydantic models for validation before write |
| DB-01 | PostgreSQL + TimescaleDB migration, asyncpg driver, hypertable for audit data | Engine config `postgresql+asyncpg://`, remove SQLite PRAGMAs, TimescaleDB `create_hypertable()` via init SQL, pool configuration |
| DB-04 | Docker Compose expansion: PostgreSQL (~200MB) + MinIO (~128MB), total < 1GB | Memory budget: PostgreSQL 256M, API 256M, Redis 64M, MinIO 128M, Nginx 32M = 680M + headroom. TimescaleDB image `timescale/timescaledb:latest-pg16` |
| AUTH-02 | Config expansion: git_repo_url, postgres_url, minio_endpoint, capability_token_secret, retention settings | Extend existing `Settings` class with pydantic-settings. New fields with sensible defaults. Replace `database_url` with `postgres_url` |
| AUTH-03 | Dependency updates: add asyncpg, gitpython, minio; remove aiosqlite | Verified versions: asyncpg 0.31.0, gitpython 3.1.50, minio 7.2.20, alembic 1.18.4 |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.49 | ORM + query builder | Already in use, stable 2.0 async API, PostgreSQL JSONB/ENUM dialect support |
| asyncpg | 0.31.0 | PostgreSQL async driver | Fastest async PG driver, binary protocol, native async, user-decided |
| alembic | 1.18.4 | Database migrations | SQLAlchemy's official migration tool, async support via `run_sync()` |
| pydantic | 2.13.3 | Data validation | Already in use, FastAPI's validation layer |
| pydantic-settings | 2.14.0 | Configuration management | Already in use, `.env` file support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| gitpython | 3.1.50 | Git repository integration | GitOps policy-as-code (Phase 17), provenance tracking |
| minio | 7.2.20 | S3-compatible object storage client | Warm storage tier (Phase 22), media asset storage |
| greenlet | 3.5.0 | Async context for SQLAlchemy | Required by `sqlalchemy[asyncio]`, already installed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncpg | psycopg (3.3.4) async | psycopg has better feature completeness and pipeline mode, but asyncpg is faster for simple queries and user-decided |
| JSONB columns | Normalized tables | Normalized = more joins, migration complexity, schema changes per template. JSONB = flexible, template-driven, read-as-unit |
| PostgreSQL ENUM | VARCHAR + CHECK | ENUM = type-safe, efficient storage. VARCHAR = easier to add values. Use ENUM for stable status fields, CHECK for evolving values |
| Alembic | create_all() in lifespan | create_all is only for dev/prototyping. Alembic is production standard for tracked schema changes |

**Installation:**
```bash
pip install asyncpg==0.31.0 alembic==1.18.4 gitpython==3.1.50 minio==7.2.20
pip uninstall aiosqlite
```

**Version verification:**
- asyncpg 0.31.0 -- PyPI verified 2026-05-16
- alembic 1.18.4 -- PyPI verified 2026-05-16
- gitpython 3.1.50 -- PyPI verified 2026-05-16
- minio 7.2.20 -- PyPI verified 2026-05-16
- SQLAlchemy 2.0.49 -- PyPI verified 2026-05-16, already installed

## Architecture Patterns

### Recommended Project Structure
```
app/
├── core/
│   ├── config.py          # Settings with postgres_url, minio_endpoint, etc.
│   ├── database.py        # Async engine + session factory (PostgreSQL)
│   └── ...
├── models/
│   ├── base.py            # DeclarativeBase only
│   ├── shot_card.py       # ShotCard SQLAlchemy model
│   ├── audit_entry.py     # AuditEntry SQLAlchemy model (TimescaleDB hypertable)
│   ├── policy_version.py  # PolicyVersion model (kept from V1)
│   └── schemas.py         # Pydantic models (request/response)
├── migrations/            # Alembic migrations directory
│   ├── env.py             # Async migration runner
│   ├── versions/          # Migration files
│   └── script.py.mako
alembic.ini                # Alembic configuration
docker-compose.yml         # Expanded with PostgreSQL + MinIO
Dockerfile                 # Updated (no SQLite data dir)
requirements.txt           # Updated dependencies
scripts/
├── init-db.sql            # TimescaleDB extension + hypertable setup
└── start.sh               # Updated startup (alembic upgrade head)
```

### Pattern 1: PostgreSQL Async Engine Configuration
**What:** Replace SQLite engine with PostgreSQL async engine using asyncpg
**When to use:** Core database connection setup
**Example:**
```python
# Source: SQLAlchemy 2.0 docs, asyncpg dialect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    "postgresql+asyncpg://review:password@postgres:5432/reviewdb",
    echo=False,
    pool_size=10,           # Concurrent connections
    max_overflow=5,         # Burst capacity
    pool_timeout=30,        # Wait for connection
    pool_recycle=1800,      # Recycle after 30min
    pool_pre_ping=True,     # Check connection health
    pool_use_lifo=True,     # Reduce idle connections
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,  # CRITICAL for async - prevents lazy-loading errors
    class_=AsyncSession,
)
```

### Pattern 2: Shot Card SQLAlchemy Model with JSONB
**What:** Single table with JSONB columns for nested structures
**When to use:** Core data model for Shot Card
**Example:**
```python
# Source: SQLAlchemy 2.0 PostgreSQL dialect docs
from sqlalchemy import String, Integer, Index, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
import enum

class AuditStatus(str, enum.Enum):
    AWAITING_AUDIT = "awaiting_audit"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_AUDIO = "pending_audio"

class RoutingDecision(str, enum.Enum):
    AUTO = "AUTO"
    HUMAN = "HUMAN"
    AI_AUDIT = "AI_AUDIT"
    BLOCK = "BLOCK"

class ShotCard(Base):
    __tablename__ = "shot_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Nested structures as JSONB
    narrative_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    visual_bundle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    audio_bundle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Status fields as ENUMs
    audit_status: Mapped[str] = mapped_column(
        SAEnum(AuditStatus, name="audit_status", create_constraint=True),
        nullable=False, default=AuditStatus.AWAITING_AUDIT
    )
    routing_decision: Mapped[str | None] = mapped_column(
        SAEnum(RoutingDecision, name="routing_decision", create_constraint=True),
        nullable=True
    )
    min_audit_set: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    blocking_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Provenance
    workflow_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_shot_cards_project_created", "project_id", "created_at"),
        Index("ix_shot_cards_status_created", "audit_status", "created_at"),
        Index("ix_shot_cards_narrative_gin", "narrative_context", postgresql_using="gin"),
        Index("ix_shot_cards_visual_gin", "visual_bundle", postgresql_using="gin"),
    )
```

### Pattern 3: TimescaleDB Hypertable for Audit Entries
**What:** Convert audit_entries table to TimescaleDB hypertable partitioned by time
**When to use:** Audit entry table initialization
**Example:**
```sql
-- init-db.sql (run via docker-entrypoint-initdb.d)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Table must be created BEFORE calling create_hypertable
-- Primary key MUST include the time column for hypertables
CREATE TABLE IF NOT EXISTS audit_entries (
    id BIGSERIAL,
    shot_card_id INTEGER NOT NULL REFERENCES shot_cards(id),
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    from_state VARCHAR(50),
    to_state VARCHAR(50),
    payload JSONB,
    prev_hash VARCHAR(64) NOT NULL,
    own_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (created_at, id)
);

SELECT create_hypertable('audit_entries', 'created_at',
    chunk_time_interval => INTERVAL '1 day',
    migrate_data => TRUE
);

-- Compression for older data
ALTER TABLE audit_entries SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'shot_card_id',
    timescaledb.compress_orderby = 'created_at DESC'
);

-- Auto-compress after 7 days
SELECT add_compression_policy('audit_entries', INTERVAL '7 days');

-- Retention policy: drop chunks older than 30 days (hot tier)
SELECT add_retention_policy('audit_entries', INTERVAL '30 days');

-- Indexes
CREATE INDEX ix_audit_shot_created ON audit_entries (shot_card_id, created_at DESC);
CREATE INDEX ix_audit_action_created ON audit_entries (action, created_at DESC);
CREATE INDEX ix_audit_actor_created ON audit_entries (actor, created_at DESC);
```

### Pattern 4: Alembic Async Migration Setup
**What:** Configure Alembic to work with asyncpg
**When to use:** Database migration lifecycle
**Example:**
```python
# migrations/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

from app.core.config import get_settings
from app.models.base import Base
# Import all models so Base.metadata is populated
from app.models.shot_card import ShotCard  # noqa: F401
from app.models.audit_entry import AuditEntry  # noqa: F401
from app.models.policy_version import PolicyVersion  # noqa: F401

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.postgres_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Pattern 5: Docker Compose Memory Budget (1GB)
**What:** Expanded Docker Compose with PostgreSQL, MinIO under 1GB total
**When to use:** Container orchestration
**Example:**
```yaml
# Memory budget: PostgreSQL 256M + API 256M + Redis 64M + MinIO 128M + Nginx 32M = 736M
# Headroom for bursts: ~264M

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: review-postgres
    environment:
      POSTGRES_USER: review
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: reviewdb
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql
    expose:
      - "5432"
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.5"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U review -d reviewdb"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    container_name: review-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    expose:
      - "9000"
      - "9001"
    volumes:
      - minio_data:/data
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: "0.25"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  api:
    # ... existing API config, updated depends_on
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    # Memory stays at 256M

  redis:
    # ... unchanged, 64M

  nginx:
    # ... unchanged, 32M

volumes:
  postgres_data: {}
  minio_data: {}
  redis_data: {}
```

### Pattern 6: Pydantic Models for Shot Card Validation
**What:** Pydantic models that validate data before writing to JSONB
**When to use:** API request/response validation, ensuring JSONB structure integrity
**Example:**
```python
from pydantic import BaseModel, Field
from typing import Literal

class Keyframe(BaseModel):
    url: str
    hash: str
    node: str

class Keyframes(BaseModel):
    first: Keyframe | None = None
    last: Keyframe | None = None

class VideoClip(BaseModel):
    url: str
    duration: float
    node: str

class Candidate(BaseModel):
    candidate_id: str
    keyframes: Keyframes
    score: float | None = None

class VisualBundle(BaseModel):
    keyframes: Keyframes | None = None
    video_clip: VideoClip | None = None
    prompt: str | None = None
    candidates: list[Candidate] = Field(default_factory=list)

class AudioBundle(BaseModel):
    bgm_prompt: str | None = None
    sfx_prompt: str | None = None
    status: Literal["pending", "ready", "failed"] = "pending"

class NarrativeContext(BaseModel):
    scene: str
    shot_number: int
    emotion_curve: str
    continuity_tags: list[str] = Field(default_factory=list)

class AuditState(BaseModel):
    status: Literal["awaiting_audit", "approved", "rejected", "pending_audio"]
    routing_decision: Literal["AUTO", "HUMAN", "AI_AUDIT", "BLOCK"] | None = None
    min_audit_set: list[str] = Field(default_factory=lambda: ["visual_bundle"])
    blocking_reason: str | None = None

class Provenance(BaseModel):
    workflow_version: str | None = None
    policy_commit_sha: str | None = None
    execution_id: str | None = None
```

### Anti-Patterns to Avoid
- **Mutable JSONB without `flag_modified()`**: SQLAlchemy does not detect in-place dict mutations on JSONB columns. Always use `flag_modified(obj, "column_name")` after mutating, or use `MutableDict.as_mutable(JSONB)`.
- **SQLite PRAGMAs on PostgreSQL**: Remove ALL `connect_args`, PRAGMA event listeners, and the SQLite authorizer. PostgreSQL has entirely different connection configuration.
- **`create_all()` in lifespan for production**: Use Alembic migrations. `create_all()` skips TimescaleDB hypertable setup, ENUM registration, and compression policies.
- **ENUM values that change frequently**: PostgreSQL ENUMs are hard to alter (cannot remove values). Use VARCHAR + CHECK constraint for fields likely to gain new values.
- **Connection pooling with `check_same_thread`**: This is SQLite-specific. PostgreSQL asyncpg handles connection pooling natively via SQLAlchemy's pool.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Database migrations | SQL scripts in lifespan | Alembic | Tracks schema history, supports upgrades/downgrades, autogenerates diffs |
| PostgreSQL ENUM management | Raw ALTER TYPE commands | SQLAlchemy `Enum()` with explicit `name=` | Alembic handles creation; shared type definition across models and migrations |
| JSONB mutation detection | Custom dirty-checking | `flag_modified()` or `MutableDict.as_mutable(JSONB)` | SQLAlchemy has built-in support; custom solutions miss edge cases |
| TimescaleDB hypertable setup | Manual SQL in app code | `init-db.sql` via `docker-entrypoint-initdb.d` | Runs once at container creation, idempotent, separate from app schema |
| Connection pool management | Custom pool logic | SQLAlchemy `pool_size`, `max_overflow`, `pool_pre_ping` | Production-tested, handles edge cases (stale connections, timeouts) |
| Audit log immutability | SQLite authorizer pattern | PostgreSQL row-level security (RLS) or trigger-based protection | PostgreSQL has native RLS; SQLite authorizer is not portable |

**Key insight:** V1 relied on SQLite-specific features (authorizer, PRAGMAs, in-memory test DB). V2 must use PostgreSQL-native equivalents. Do not try to port SQLite patterns.

## Common Pitfalls

### Pitfall 1: JSONB Mutation Detection
**What goes wrong:** Modifying a JSONB dict in-place (e.g., `shot_card.visual_bundle["keyframes"]["first"] = {...}`) does NOT trigger SQLAlchemy's dirty tracking. The change is silently lost on commit.
**Why it happens:** SQLAlchemy tracks column-level changes, not in-place mutations of mutable Python objects.
**How to avoid:** Either (1) use `flag_modified(obj, "visual_bundle")` after mutation, or (2) use `MutableDict.as_mutable(JSONB)` wrapper, or (3) assign a new dict entirely (`obj.visual_bundle = {...modified...}`).
**Warning signs:** Data appears correct in Python but is missing from database after page reload.

### Pitfall 2: PostgreSQL ENUM Migration Complexity
**What goes wrong:** Adding a new value to a PostgreSQL ENUM requires `ALTER TYPE ... ADD VALUE`, which cannot run inside a transaction in PostgreSQL < 12. Removing a value requires recreating the entire ENUM type.
**Why it happens:** PostgreSQL ENUMs are database-level types with strict immutability.
**How to avoid:** Only use ENUMs for truly stable status fields (audit_status, routing_decision). For values that may grow, use VARCHAR with CHECK constraints or validate via Pydantic.
**Warning signs:** Alembic autogenerate does not detect ENUM value changes; manual migration editing required.

### Pitfall 3: TimescaleDB Hypertable Primary Key
**What goes wrong:** `create_hypertable()` fails if the primary key does not include the partition column (time column).
**Why it happens:** TimescaleDB requires the time column in all unique constraints for partition alignment.
**How to avoid:** Define primary keys as `(created_at, id)` for hypertables. Use `BIGSERIAL` instead of `SERIAL` for audit tables (high-volume append).
**Warning signs:** `create_hypertable` error: "cannot create hypertable because the table has a unique index that does not include the partition column."

### Pitfall 4: Docker Compose Startup Ordering
**What goes wrong:** API container starts before PostgreSQL is ready, causing connection failures and crash loops.
**Why it happens:** PostgreSQL takes 10-30 seconds to initialize on first run (creating database, running init scripts).
**How to avoid:** Use `healthcheck` with `pg_isready` and `depends_on: condition: service_healthy`. Set `start_period: 30s` for PostgreSQL healthcheck. In `start.sh`, run `alembic upgrade head` before starting uvicorn.
**Warning signs:** API container logs "connection refused" or "database does not exist" on fresh `docker compose up`.

### Pitfall 5: Alembic Async Configuration
**What goes wrong:** Alembic's default `env.py` uses synchronous database connections. Running with `postgresql+asyncpg://` URL causes errors.
**Why it happens:** Alembic was originally designed for synchronous drivers.
**How to avoid:** Replace `env.py` with async version using `asyncio.run()` + `run_sync()` pattern. Use `pool.NullPool` to avoid connection pool conflicts.
**Warning signs:** `TypeError` or `NotImplementedError` when running `alembic upgrade head`.

### Pitfall 6: Memory Budget Overrun
**What goes wrong:** Adding PostgreSQL (256M) + MinIO (128M) to existing containers pushes total memory past 1GB.
**Why it happens:** PostgreSQL's `shared_buffers` defaults to 128MB, and work_mem per connection adds up. MinIO's Go runtime has overhead.
**How to avoid:** Set explicit `memory` limits in Docker Compose. Tune PostgreSQL: `shared_buffers=64MB` for 256M container. Set MinIO `--no-checksum` if not needed.
**Warning signs:** OOM kills on the host machine, containers restarting unexpectedly.

## Code Examples

### Updated Settings Class
```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    postgres_url: str = "postgresql+asyncpg://review:review@postgres:5432/reviewdb"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "review-platform"
    minio_secure: bool = False

    # Git
    git_repo_url: str = ""
    git_branch: str = "main"

    # Auth
    api_key: str
    jwt_secret: str
    capability_token_secret: str = ""

    # General
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # Review settings
    review_timeout_minutes: int = 1440
    ai_audit_timeout_minutes: int = 5

    # Retention (days)
    hot_retention_days: int = 30
    warm_retention_days: int = 365

    # Telegram (kept for Phase 22)
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

### Updated database.py
```python
# app/core/database.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.postgres_url,
    echo=settings.log_level == "DEBUG",
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_use_lifo=True,
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
```

### Updated start.sh
```bash
#!/bin/bash
set -e

# Run database migrations
alembic upgrade head

# Start the application
exec "$@"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `aiosqlite` driver | `asyncpg` driver | Phase 15 (V2) | Binary protocol, faster, connection pooling |
| SQLite `PRAGMA` tuning | PostgreSQL `postgresql.conf` tuning | Phase 15 (V2) | `shared_buffers`, `work_mem`, `effective_cache_size` |
| `create_all()` in lifespan | Alembic migrations | Phase 15 (V2) | Schema versioning, upgrade/downgrade support |
| SQLite authorizer | PostgreSQL RLS or triggers | Phase 15 (V2) | Standard PostgreSQL security model |
| Flat Review model | Nested Shot Card with JSONB | Phase 15 (V2) | Rich domain model, flexible schema |
| In-memory SQLite for tests | PostgreSQL test fixtures or SQLite fallback | Phase 15 (V2) | Tests need PostgreSQL or careful SQLite compatibility |

**Deprecated/outdated:**
- `aiosqlite`: Removed entirely. asyncpg replaces it.
- SQLite-specific PRAGMAs: Not applicable to PostgreSQL.
- SQLite `set_authorizer` audit protection: Replace with PostgreSQL RLS or trigger-based approach.
- `database_url` setting: Replaced by `postgres_url`.

## Open Questions

1. **TimescaleDB image tag stability**
   - What we know: `timescale/timescaledb:latest-pg16` exists on Docker Hub
   - What's unclear: Exact latest version number, whether PG17 is supported
   - Recommendation: Pin to `timescale/timescaledb:2.x-pg16` once verified on Docker Hub. For now, `latest-pg16` is acceptable for LAN deployment.

2. **Test database strategy for V2**
   - What we know: V1 tests use in-memory SQLite. V2 models use PostgreSQL-specific features (JSONB, ENUM).
   - What's unclear: Whether to use PostgreSQL test containers, SQLite fallback for unit tests, or mock the database layer.
   - Recommendation: Use SQLite for unit tests (most JSONB operations have SQLite JSON fallback). Use PostgreSQL test container for integration tests. Phase scope: unit tests only, integration tests deferred.

3. **Audit immutability mechanism for PostgreSQL**
   - What we know: V1 used SQLite `set_authorizer` to block UPDATE/DELETE on audit_entries. PostgreSQL has no direct equivalent.
   - What's unclear: Whether RLS (row-level security) or trigger-based approach is better for this use case.
   - Recommendation: Use a simple BEFORE UPDATE/DELETE trigger that raises an exception. This is simpler than RLS and equally effective for single-application databases. Not strictly Phase 15 scope but the trigger should be part of init-db.sql.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container builds & runtime | Yes | 29.4.3 | -- |
| Python 3.12 | Runtime | Yes | 3.12.3 | -- |
| git | GitPython (Phase 17) | Yes | 2.43.0 | -- |
| Node.js | GSD tooling only | Yes | 24.13.0 | -- |
| PostgreSQL | Database | Container | timescale/timescaledb:latest-pg16 | -- |
| MinIO | Object storage | Container | minio/minio:latest | -- |
| Redis 7 | Cache/queue | Container | redis:7-alpine | -- |

**Missing dependencies with no fallback:**
- None. All dependencies are containerized.

**Missing dependencies with fallback:**
- None.

## Sources

### Primary (HIGH confidence)
- PyPI registry (pip3 index versions) -- asyncpg 0.31.0, alembic 1.18.4, gitpython 3.1.50, minio 7.2.20, SQLAlchemy 2.0.49
- SQLAlchemy 2.0 documentation -- async engine, PostgreSQL dialect, JSONB type, mapped_column patterns
- TimescaleDB documentation -- hypertable setup, compression policies, retention policies
- V2-ARCHITECTURE.md -- Shot Card data model YAML structure (authoritative for field definitions)
- V2-GAP-ANALYSIS.md -- GAP-2.1, GAP-4.1, GAP-CC.3, GAP-CC.4, GAP-CC.5 (authoritative gap identification)

### Secondary (MEDIUM confidence)
- asyncpg vs psycopg3 performance comparison -- training data (general consensus: asyncpg faster for simple queries, psycopg3 more feature-complete)
- MinIO Docker memory footprint -- training data (~50-300MB typical)
- PostgreSQL ENUM migration complexity -- training data (ALTER TYPE limitations, removal requires type recreation)

### Tertiary (LOW confidence)
- TimescaleDB exact memory usage in 256M container -- not directly verified, estimate based on PostgreSQL + extension overhead

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified against PyPI, existing codebase patterns well-understood
- Architecture: HIGH -- JSONB + single-table Shot Card is standard pattern for semi-structured data, TimescaleDB hypertable is the standard approach for time-series audit data
- Pitfalls: HIGH -- JSONB mutation detection, ENUM migration complexity, and hypertable primary key requirements are well-documented PostgreSQL/SQLAlchemy gotchas
- Docker memory budget: MEDIUM -- estimates based on training data for MinIO and PostgreSQL; actual usage may vary

**Research date:** 2026-05-16
**Valid until:** 2026-06-16 (stable -- PostgreSQL/SQLAlchemy/TimescaleDB are mature technologies)
