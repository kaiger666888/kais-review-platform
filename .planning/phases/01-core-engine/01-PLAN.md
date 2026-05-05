---
phase: 01-core-engine
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - app/__init__.py
  - app/main.py
  - app/core/__init__.py
  - app/core/config.py
  - app/core/database.py
  - app/core/audit.py
  - app/models/__init__.py
  - app/models/schema.py
  - app/models/schemas.py
  - requirements.txt
  - .env.example
autonomous: true
requirements:
  - AUDT-01
  - AUDT-02
  - AUDT-03

must_haves:
  truths:
    - "FastAPI application starts without errors and health endpoint returns 200"
    - "SQLite database initializes with WAL mode, busy_timeout=5000, and foreign keys enabled"
    - "Audit entries can be appended but UPDATE and DELETE are rejected at SQLite connection level"
    - "All Pydantic request/response models exist with correct field types and validation"
  artifacts:
    - path: "app/main.py"
      provides: "FastAPI application factory with lifespan context manager"
      exports: ["app"]
    - path: "app/core/config.py"
      provides: "Pydantic Settings configuration from .env"
      exports: ["Settings", "get_settings"]
    - path: "app/core/database.py"
      provides: "SQLAlchemy async engine + session factory with WAL pragmas"
      exports: ["engine", "async_session_factory", "get_db"]
    - path: "app/core/audit.py"
      provides: "Immutable audit logger with hash chain"
      exports: ["AuditLogger"]
    - path: "app/models/schema.py"
      provides: "SQLAlchemy models for reviews, audit_entries, policy_versions"
      exports: ["Review", "AuditEntry", "PolicyVersion", "create_tables"]
    - path: "app/models/schemas.py"
      provides: "Pydantic request/response models for all API endpoints"
      exports: ["ReviewCreateRequest", "ReviewResponse", "AuditEntryResponse", "PaginatedResponse"]
    - path: "requirements.txt"
      provides: "All Python dependencies with pinned versions"
    - path: ".env.example"
      provides: "Template for environment variables"
  key_links:
    - from: "app/core/database.py"
      to: "app/models/schema.py"
      via: "import Base, create_tables"
      pattern: "from app\\.models\\.schema import.*create_tables"
    - from: "app/core/audit.py"
      to: "app/core/database.py"
      via: "AsyncSession dependency"
      pattern: "from app\\.core\\.database import.*AsyncSession"
    - from: "app/main.py"
      to: "app/core/database.py"
      via: "lifespan init creates tables"
      pattern: "run_sync.*create_tables"
---

<objective>
Create the project foundation: FastAPI app skeleton, async SQLite database layer with WAL mode, all SQLAlchemy models, all Pydantic schemas, and the immutable audit trail logger with hash chain.

Purpose: Every subsequent plan depends on this foundation. The database schema, session factory, and audit trail are the bedrock of the entire platform. Getting SQLite WAL mode + aiosqlite + optimistic locking right from day one prevents "database is locked" errors and race conditions later.

Output: Working FastAPI application that starts, initializes SQLite with correct pragmas, and provides an audit logger that is append-only by design.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-core-engine/01-CONTEXT.md
@.planning/phases/01-core-engine/01-RESEARCH.md
@.planning/research/PITFALLS.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create project skeleton with FastAPI, config, and database layer</name>
  <files>app/__init__.py, app/main.py, app/core/__init__.py, app/core/config.py, app/core/database.py, requirements.txt, .env.example</files>
  <read_first>
    - .planning/phases/01-core-engine/01-RESEARCH.md (Pattern 1: Async SQLite Session Factory, Pattern 6: FastAPI Lifespan)
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: .env + Pydantic Settings, app/core/ layout)
    - .planning/research/PITFALLS.md (Pitfall 1: SQLite concurrent writes)
  </read_first>
  <action>
1. Create `requirements.txt` with these exact pinned versions:
   ```
   fastapi==0.136.1
   uvicorn[standard]==0.46.0
   pydantic==2.13.3
   pydantic-settings==2.14.0
   sqlalchemy[asyncio]==2.0.49
   aiosqlite==0.22.1
   redis==7.4.0
   arq==0.28.0
   PyJWT==2.12.1
   PyYAML==6.0.2
   jsonschema==4.23.0
   structlog==25.5.0
   httpx==0.28.1
   pytest==8.3.5
   pytest-asyncio==0.24.0
   ```

2. Create `.env.example` with these variables:
   ```
   API_KEY=change-me-in-production
   JWT_SECRET=change-me-in-production
   REDIS_URL=redis://localhost:6379/0
   DATABASE_URL=sqlite+aiosqlite:///./data/review.db
   LOG_LEVEL=INFO
   ```

3. Create `app/core/config.py` using pydantic-settings:
   - Class `Settings(BaseSettings)` with fields:
     - `api_key: str` (env="API_KEY")
     - `jwt_secret: str` (env="JWT_SECRET")
     - `redis_url: str = "redis://localhost:6379/0"` (env="REDIS_URL")
     - `database_url: str = "sqlite+aiosqlite:///./data/review.db"` (env="DATABASE_URL")
     - `log_level: str = "INFO"` (env="LOG_LEVEL")
   - `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`
   - Function `get_settings() -> Settings` that returns a cached instance

4. Create `app/core/database.py`:
   - `engine = create_async_engine(DATABASE_URL, connect_args={"check_same_thread": False})`
   - Use SQLAlchemy `event.listens_for(engine.sync_engine, "connect")` to apply pragmas on every new connection:
     ```python
     @event.listens_for(engine.sync_engine, "connect")
     def set_sqlite_pragma(dbapi_connection, connection_record):
         cursor = dbapi_connection.cursor()
         cursor.execute("PRAGMA journal_mode=WAL")
         cursor.execute("PRAGMA busy_timeout=5000")
         cursor.execute("PRAGMA foreign_keys=ON")
         cursor.close()
     ```
   - `async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`
   - Async generator `get_db() -> AsyncGenerator[AsyncSession, None]` that yields sessions with `async with async_session_factory() as session`

5. Create `app/__init__.py` and `app/core/__init__.py` as empty files.

6. Create `app/main.py`:
   - Use `@asynccontextmanager` lifespan to:
     a. Run `async with engine.begin() as conn: await conn.run_sync(create_tables)` to initialize schema
     b. Create Redis connection: `aioredis.from_url(settings.redis_url, decode_responses=True)` stored in `app.state.redis`
     c. Create arq pool: `await create_pool(RedisSettings.from_dsn(settings.redis_url))` stored in `app.state.arq_pool`
     d. On shutdown: close redis, close arq_pool, dispose engine
   - Create `FastAPI(lifespan=lifespan, title="Kai's Review Platform", version="1.0.0")`
   - Add `GET /health` endpoint returning `{"status": "ok"}`
   - Import and include routers placeholder (will be added in later plans)
   - `get_redis` dependency that returns `request.app.state.redis`
   - `get_arq_pool` dependency that returns `request.app.state.arq_pool`
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && pip install -r requirements.txt 2>&1 | tail -5 && python -c "from app.core.config import Settings; s = Settings(api_key='test', jwt_secret='test'); print(f'Settings OK: {s.api_key[:4]}...')" && python -c "from app.core.database import engine, async_session_factory; print('Database module OK')" && echo "All imports successful"</automated>
  </verify>
  <done>
    - requirements.txt exists with all pinned versions
    - .env.example exists with all required env vars
    - `from app.core.config import Settings` succeeds
    - `from app.core.database import engine, async_session_factory, get_db` succeeds
    - `from app.main import app` succeeds
    - Settings loads from .env file
  </done>
</task>

<task type="auto">
  <name>Task 2: Define SQLAlchemy models and Pydantic schemas</name>
  <files>app/models/__init__.py, app/models/schema.py, app/models/schemas.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: flexible JSON metadata + typed columns, cursor-based pagination)
    - .planning/phases/01-core-engine/01-RESEARCH.md (Pattern 2: Optimistic Locking, Pattern 5: Immutable Audit Trail)
  </read_first>
  <action>
1. Create `app/models/schema.py` with SQLAlchemy models using `DeclarativeBase`:

   **Base class:**
   ```python
   class Base(DeclarativeBase):
       pass
   ```

   **Review model:**
   - Table name: `reviews`
   - `id: Mapped[int]` = primary key, autoincrement (INTEGER PRIMARY KEY)
   - `type: Mapped[str]` = not null, max 50 chars (e.g., "scene_image", "text_content")
   - `content_ref: Mapped[str]` = not null (URL/path to content)
   - `metadata_json: Mapped[dict | None]` = JSON column for flexible metadata
   - `source_system: Mapped[str]` = not null (e.g., "kais-movie-agent", "kais-gold-team")
   - `priority: Mapped[str]` = not null, default "normal" (values: "low", "normal", "high", "critical")
   - `risk_score: Mapped[float | None]` = nullable float 0.0-1.0
   - `state: Mapped[str]` = not null, default "PENDING" (values: PENDING, POLICY_EVAL, APPROVING, COMPLETE)
   - `disposition: Mapped[str | None]` = nullable (AUTO, HUMAN, AI_AUDIT, BLOCK)
   - `version: Mapped[int]` = not null, default 1 (for optimistic locking)
   - `created_at: Mapped[datetime]` = default func.now()
   - `updated_at: Mapped[datetime]` = default func.now(), onupdate func.now()
   - Index on `(state, created_at)` for list queries
   - Index on `(source_system, created_at)` for source filtering

   **AuditEntry model:**
   - Table name: `audit_entries`
   - `id: Mapped[int]` = primary key, autoincrement
   - `review_id: Mapped[int]` = not null, foreign key to reviews.id
   - `action: Mapped[str]` = not null (submit, route, approve, reject, escalate, expire, policy_change)
   - `actor: Mapped[str]` = not null (policy_engine, system, or "client:{client_id}")
   - `from_state: Mapped[str | None]` = nullable
   - `to_state: Mapped[str | None]` = nullable
   - `payload: Mapped[dict | None]` = JSON column for arbitrary metadata
   - `prev_hash: Mapped[str]` = not null (SHA-256 of previous audit entry)
   - `own_hash: Mapped[str]` = not null (SHA-256 of this entry, computed after insert)
   - `created_at: Mapped[datetime]` = default func.now()
   - Index on `(review_id, created_at)` for review history queries
   - Index on `(created_at, action)` for filtered audit queries
   - Index on `(actor, created_at)` for actor-based queries

   **PolicyVersion model:**
   - Table name: `policy_versions`
   - `id: Mapped[int]` = primary key, autoincrement
   - `name: Mapped[str]` = not null, unique (policy name, e.g., "default_routing")
   - `version: Mapped[str]` = not null (semantic version, e.g., "1.0")
   - `content: Mapped[str]` = not null (raw YAML content)
   - `is_active: Mapped[bool]` = default True
   - `created_at: Mapped[datetime]` = default func.now()
   - `updated_at: Mapped[datetime]` = default func.now(), onupdate func.now()

   **create_tables function:**
   ```python
   def create_tables(conn):
       Base.metadata.create_all(conn)
   ```

2. Create `app/models/schemas.py` with Pydantic models:

   **ReviewState enum:**
   ```python
   class ReviewState(str, Enum):
       PENDING = "PENDING"
       POLICY_EVAL = "POLICY_EVAL"
       APPROVING = "APPROVING"
       COMPLETE = "COMPLETE"
   ```

   **Disposition enum:**
   ```python
   class Disposition(str, Enum):
       AUTO = "AUTO"
       HUMAN = "HUMAN"
       AI_AUDIT = "AI_AUDIT"
       BLOCK = "BLOCK"
   ```

   **Request models:**
   - `ReviewCreateRequest`: type (str, min_length=1, max_length=50), content_ref (str, min_length=1), metadata (dict | None = None), source_system (str, min_length=1), priority (str = "normal", pattern="^(low|normal|high|critical)$"), risk_score (float | None = None, ge=0.0, le=1.0)
   - `ApproveRequest`: comment (str | None = None)
   - `RejectRequest`: reason (str, min_length=1, max_length=500)
   - `TokenRequest`: api_key (str), client_id (str)
   - `PolicyCreateRequest`: name (str), content (str) -- raw YAML
   - `PolicyUpdateRequest`: content (str) -- raw YAML

   **Response models:**
   - `ReviewResponse`: id, type, content_ref, metadata, source_system, priority, risk_score, state, disposition, version, created_at, updated_at
   - `ReviewSubmitResponse`: review_id (int), state (str), routing (str | None)
   - `AuditEntryResponse`: id, review_id, action, actor, from_state, to_state, payload, created_at
   - `PolicyResponse`: name, version, is_active, created_at, updated_at
   - `PaginatedResponse[T]` (generic): items (list[T]), next_cursor (int | None), has_more (bool)
   - `ErrorResponse`: error (str), detail (str | None)

   **Envelope models:**
   - `ApiResponse[T]` (generic): data (T | None = None), meta (dict | None = None), error (ErrorResponse | None = None)

3. Create `app/models/__init__.py` re-exporting key types.
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.models.schema import Base, Review, AuditEntry, PolicyVersion, create_tables
from app.models.schemas import ReviewState, Disposition, ReviewCreateRequest, ApproveRequest, RejectRequest, ApiResponse, PaginatedResponse
print(f'Models OK: {Review.__tablename__}, {AuditEntry.__tablename__}, {PolicyVersion.__tablename__}')
print(f'Schemas OK: states={[s.value for s in ReviewState]}, dispositions={[d.value for d in Disposition]}')
# Verify Review has version column
assert hasattr(Review, 'version'), 'Review must have version column'
# Verify AuditEntry has hash columns
assert hasattr(AuditEntry, 'prev_hash'), 'AuditEntry must have prev_hash'
assert hasattr(AuditEntry, 'own_hash'), 'AuditEntry must have own_hash'
print('All model assertions passed')
"</automated>
  </verify>
  <done>
    - SQLAlchemy models exist for reviews, audit_entries, policy_versions tables
    - Review model has version column for optimistic locking
    - AuditEntry model has prev_hash and own_hash for hash chain
    - ReviewState enum has exactly 4 values: PENDING, POLICY_EVAL, APPROVING, COMPLETE
    - Disposition enum has 4 values: AUTO, HUMAN, AI_AUDIT, BLOCK
    - All Pydantic request models have field validation
    - PaginatedResponse is generic with items, next_cursor, has_more
  </done>
</task>

<task type="auto">
  <name>Task 3: Implement immutable audit trail logger with hash chain</name>
  <files>app/core/audit.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-RESEARCH.md (Pattern 5: Immutable Audit Trail)
    - .planning/research/PITFALLS.md (Pitfall: Mutable Audit Entries)
    - app/models/schema.py (AuditEntry model created in Task 2)
    - app/core/database.py (session factory created in Task 1)
  </read_first>
  <action>
1. Create `app/core/audit.py` with `AuditLogger` class:

   **Class `AuditLogger`:**
   - Constructor takes no special arguments (uses get_db or session parameter)
   - Method `async log(session: AsyncSession, review_id: int, action: str, actor: str, from_state: str | None = None, to_state: str | None = None, payload: dict | None = None) -> AuditEntry`:
     a. Query the last audit entry for this review_id (ordered by id DESC, limit 1) to get prev_hash. If no previous entry, prev_hash = "0" * 64 (64 zeros).
     b. Create AuditEntry with all fields EXCEPT own_hash (set own_hash to placeholder "pending").
     c. Add to session, flush to get the auto-increment id.
     d. Compute own_hash = SHA-256 of string: `f"{entry.id}:{entry.review_id}:{entry.action}:{entry.actor}:{entry.from_state}:{entry.to_state}:{entry.prev_hash}:{entry.created_at.isoformat()}"` using hashlib.sha256.
     e. Update entry.own_hash with computed value.
     f. Commit and return the entry.

   **SQLite authorizer for append-only protection:**
   - Module-level function `audit_protect_authorizer(action, arg1, arg2, arg3, arg4)`:
     - If `action == sqlite3.SQLITE_UPDATE and arg1 == "audit_entries"`: return `sqlite3.SQLITE_DENY`
     - If `action == sqlite3.SQLITE_DELETE and arg1 == "audit_entries"`: return `sqlite3.SQLITE_DENY`
     - Otherwise: return `sqlite3.SQLITE_OK`
   - NOTE: This authorizer will be registered in `app/core/database.py` via the existing connect event listener. Add this line to the existing `set_sqlite_pragma` function:
     ```python
     from app.core.audit import audit_protect_authorizer
     dbapi_connection.set_authorizer(audit_protect_authorizer)
     ```
   - IMPORTANT: Update `app/core/database.py` to import and register the authorizer. The function `set_sqlite_pragma` in database.py must call `dbapi_connection.set_authorizer(audit_protect_authorizer)` AFTER the pragma calls.

   **Module-level convenience function:**
   - `async def append_audit(session, review_id, action, actor, **kwargs) -> AuditEntry`: creates AuditLogger instance and calls log().

2. After creating audit.py, update `app/core/database.py` to import the authorizer and register it in the `set_sqlite_pragma` event listener. Add this import at the top:
   ```python
   from app.core.audit import audit_protect_authorizer
   ```
   And add this line inside `set_sqlite_pragma`, after the cursor.close():
   ```python
   dbapi_connection.set_authorizer(audit_protect_authorizer)
   ```
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.schema import Base, AuditEntry, create_tables
from app.core.audit import AuditLogger, audit_protect_authorizer
import sqlite3

# Verify authorizer blocks UPDATE and DELETE
assert audit_protect_authorizer(sqlite3.SQLITE_UPDATE, 'audit_entries', '', '', '') == sqlite3.SQLITE_DENY
assert audit_protect_authorizer(sqlite3.SQLITE_DELETE, 'audit_entries', '', '', '') == sqlite3.SQLITE_DENY
assert audit_protect_authorizer(sqlite3.SQLITE_INSERT, 'audit_entries', '', '', '') == sqlite3.SQLITE_OK
assert audit_protect_authorizer(sqlite3.SQLITE_SELECT, 'reviews', '', '', '') == sqlite3.SQLITE_OK
print('Authorizer tests passed')

# Verify AuditLogger can create entries
async def test():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', connect_args={'check_same_thread': False})
    async with engine.begin() as conn:
        await conn.run_sync(create_tables)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        logger = AuditLogger()
        entry = await logger.log(session, review_id=1, action='submit', actor='test', from_state=None, to_state='PENDING')
        assert entry.prev_hash == '0' * 64, f'Expected 64 zeros, got {entry.prev_hash}'
        assert len(entry.own_hash) == 64, f'Expected 64 char hash, got {len(entry.own_hash)}'
        assert entry.own_hash != entry.prev_hash, 'own_hash must differ from prev_hash'
        
        # Second entry should chain to first
        entry2 = await logger.log(session, review_id=1, action='route', actor='policy_engine', from_state='PENDING', to_state='POLICY_EVAL')
        assert entry2.prev_hash == entry.own_hash, 'Hash chain must link entries'
        print(f'Audit chain: {entry.own_hash[:16]}... -> {entry2.own_hash[:16]}...')
    await engine.dispose()

asyncio.run(test())
print('Audit logger tests passed')
"</automated>
  </verify>
  <done>
    - AuditLogger.log() creates immutable audit entries with SHA-256 hash chain
    - First entry in chain has prev_hash of 64 zeros
    - Subsequent entries chain prev_hash to previous entry's own_hash
    - SQLite authorizer blocks UPDATE and DELETE on audit_entries table
    - Authorizer is registered in database.py connect event listener
  </done>
</task>

</tasks>

<verification>
1. `pip install -r requirements.txt` succeeds
2. `from app.main import app` succeeds
3. `from app.models.schema import Review, AuditEntry, PolicyVersion` succeeds
4. `from app.models.schemas import ReviewState, Disposition, ReviewCreateRequest` succeeds
5. AuditLogger creates entries with valid hash chain
6. SQLite authorizer rejects UPDATE/DELETE on audit_entries
</verification>

<success_criteria>
- FastAPI app initializes without errors
- SQLite creates with WAL mode, busy_timeout=5000, foreign_keys=ON
- All 3 SQLAlchemy models (Review, AuditEntry, PolicyVersion) exist with correct columns
- All Pydantic schemas exist with validation
- AuditLogger creates entries with SHA-256 hash chain
- SQLite authorizer blocks UPDATE/DELETE on audit_entries
- GET /health returns {"status": "ok"}
</success_criteria>

<output>
After completion, create `.planning/phases/01-core-engine/01-SUMMARY.md`
</output>
