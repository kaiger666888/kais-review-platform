# Phase 19: AI Audit & Capability Tokens - Research

**Researched:** 2026-05-16
**Domain:** AI scoring plugin architecture, capability token (JWT) issuance/verification, PostgreSQL table design for A/B testing
**Confidence:** HIGH

## Summary

Phase 19 creates the AI audit Phase 0 infrastructure -- a scoring plugin bus that returns empty vectors, a shadow mode recorder that runs alongside human decisions, a model registry placeholder, a feedback loop writing to MinIO cold storage, an A/B test interface, and capability tokens that gate downstream GPU execution after approval. All implementations are verified stubs returning correct empty/placeholder data, designed with clean interfaces for future Phase 1-4 AI integration.

The scoring bus uses an abstract `ScoringPlugin` protocol class with a single `NullScoringPlugin` returning null scores across 5 dimensions (aesthetics, consistency, compliance, technical_quality, audio_match). Shadow mode hooks into the post-review flow via arq background tasks. Capability tokens are JWTs issued on approval with single-use semantics enforced by Redis TTL. A/B test pairs live in a dedicated `ab_test_pairs` PostgreSQL table.

**Primary recommendation:** Follow the established service/worker/model patterns exactly. The scoring bus is a new `app/services/scoring_bus.py` service. The token service extends existing `app/core/auth.py` JWT patterns. New PostgreSQL table `ab_test_pairs` and `shadow_scores` require an Alembic migration. MinIO feedback writing is a new arq worker task.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Plugin protocol class -- abstract `ScoringPlugin` with `name`, `version`, `score(shot_card) -> ScoreVector`, registered via list in Settings
- Single `NullScoringPlugin` returns empty vectors in Phase 0, extensible later
- 5 score dimensions: aesthetics, consistency, compliance, technical_quality, audio_match -- each returns `null` in Phase 0
- In-memory `ModelRegistry` dict -- `get_model(name) -> ModelInfo` returns `model_unavailable` for all queries, no database needed
- Shadow mode triggers after every human review decision via arq background task, writes to `shadow_scores` table alongside human decision
- JWT format for capability tokens -- reuses existing PyJWT dependency, `capability_token_secret` already in Settings
- Capability token payload: `shot_id`, `node_scope` (flat list of authorized node IDs), `issued_at`, `expires_at`
- Single-use tokens -- issued on approval, verified once by downstream, then invalidated. Redis TTL 1hr auto-expiry
- Verification endpoint: `POST /api/v1/tokens/verify` -- accepts token string, returns `{valid, shot_id, node_scope, expires_at}` or `{valid: false, reason}`. Checks Redis for revocation
- PostgreSQL table `ab_test_pairs` -- columns: `batch_id`, `shot_id`, `ai_score` (JSONB), `human_decision`, `created_at`, queryable by `batch_id`
- Feedback loop writes to MinIO cold storage JSONL: `{bucket}/feedback/{date}/{project_id}.jsonl` -- no PostgreSQL write for feedback (Phase 22 handles tiered storage)
- A/B batch creation via API endpoint only -- `POST /api/v1/ab-tests` accepts list of shot_ids, creates batch, returns `batch_id`

### Claude's Discretion
- Implementation details for scoring bus internals, error handling patterns, and test structure are at Claude's discretion.

### Deferred Ideas (OUT OF SCOPE)
- None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ROUT-02 | Capability Token -- issued after approval, OpenClaw execution layer validates token before allowing high-cost GPU tasks | JWT issuance/verification in auth module, Redis single-use revocation, verification endpoint |
| AI-01 | AI Audit Phase 0 -- scoring plugin bus returns empty vectors (5 dimensions), route fallback to human | ScoringPlugin protocol, NullScoringPlugin, ScoreVector Pydantic model |
| AI-02 | Shadow mode -- AI scoring runs continuously without affecting decisions, records results for training | arq background task, shadow_scores table, post-review hook |
| AI-03 | Model registry (placeholder) -- empty registry, returns model_unavailable | In-memory dict ModelRegistry, ModelInfo Pydantic model |
| AI-04 | Feedback loop (placeholder) -- human review results to cold storage for future training | MinIO JSONL writer arq task, feedback path schema |
| AI-05 | A/B test interface (placeholder) -- reserved data format, same batch of Shot Cards sent to both AI and human | ab_test_pairs table, batch creation endpoint, queryable by batch_id |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyJWT | 2.12.1 | Capability token issuance/validation | Already installed, CVE-safe (>=2.11.0), HS256 algorithm matches existing JWT pattern |
| SQLAlchemy | 2.0.49 | ORM for new tables (shadow_scores, ab_test_pairs) | Existing project standard, async engine support |
| Pydantic | 2.13.3 | ScoreVector, ModelInfo, token payload models | Existing project standard, FastAPI validation layer |
| redis-py | 5.3.1 | Token revocation, single-use enforcement | Existing project standard, `redis.asyncio` module |
| arq | 0.28.0 | Shadow mode task, feedback loop task | Existing project standard, shares FastAPI event loop |
| asyncpg | 0.31.0 | PostgreSQL async driver | Already installed, required by SQLAlchemy async engine |

### Supporting (Not Yet Installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| minio | latest | Feedback data cold storage writes | Phase 19 AI-04 feedback loop stub |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| minio Python client | httpx direct S3 API calls | minio client handles auth, retries, multipart -- httpx would need manual S3 signing |
| PostgreSQL shadow_scores table | Redis-only shadow scores | Redis loses data on restart; PostgreSQL persists for future training analysis |

**Installation:**
```bash
pip install minio
```

**Version verification:**
```bash
pip show PyJWT   # 2.12.1 (confirmed installed)
pip show minio   # NOT installed -- needs installation
```

## Architecture Patterns

### Recommended Project Structure
```
app/
├── core/
│   ├── auth.py          # EXTEND: add capability token functions
│   └── config.py        # EXTEND: add scoring_plugins list setting
├── models/
│   ├── shadow_score.py  # NEW: SQLAlchemy model for shadow_scores table
│   ├── ab_test_pair.py  # NEW: SQLAlchemy model for ab_test_pairs table
│   └── schemas.py       # EXTEND: add ScoreVector, ModelInfo, token schemas
├── services/
│   ├── scoring_bus.py   # NEW: ScoringPlugin protocol + NullScoringPlugin + ScoringBus
│   └── model_registry.py # NEW: in-memory ModelRegistry placeholder
├── api/v1/
│   ├── tokens.py        # NEW: POST /api/v1/tokens/verify endpoint
│   └── ab_tests.py      # NEW: POST /api/v1/ab-tests endpoint + GET query
└── workers/
    ├── tasks.py         # EXTEND: add shadow_score_record + feedback_write tasks
    └── __init__.py      # Already empty (workers registered in tasks.py WorkerSettings)
alembic/versions/
    └── 002_shadow_and_ab_tables.py  # NEW: migration for shadow_scores + ab_test_pairs
```

### Pattern 1: Abstract ScoringPlugin Protocol
**What:** Protocol class for AI scoring plugins, extensible for future Phase 1-4 AI models.
**When to use:** All AI scoring in Phase 0 and beyond.
**Example:**
```python
# Source: established pattern from checkpoint_types.py (Pydantic + ABC)
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Literal

class ScoreVector(BaseModel):
    """Multi-dimensional scoring result from an AI audit plugin."""
    aesthetics: float | None = None
    consistency: float | None = None
    compliance: float | None = None
    technical_quality: float | None = None
    audio_match: float | None = None
    plugin_name: str = ""
    plugin_version: str = ""

class ScoringPlugin(ABC):
    """Abstract base for scoring plugins registered with the scoring bus."""
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    async def score(self, shot_card) -> ScoreVector: ...

class NullScoringPlugin(ScoringPlugin):
    """Phase 0 placeholder: returns null scores for all dimensions."""
    @property
    def name(self) -> str:
        return "null_scorer"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def score(self, shot_card) -> ScoreVector:
        return ScoreVector(plugin_name=self.name, plugin_version=self.version)
```

### Pattern 2: Capability Token as JWT with Redis Revocation
**What:** Reuses existing PyJWT + Redis patterns from `app/core/auth.py` for single-use capability tokens.
**When to use:** After Shot Card approval, before downstream GPU execution.
**Example:**
```python
# Source: extends pattern from app/core/auth.py create_jwt/decode_jwt + consume_review_token

async def issue_capability_token(
    redis: aioredis.Redis,
    shot_id: str,
    node_scope: list[str],
    secret: str,
    ttl: int = 3600,  # 1 hour
) -> str:
    """Issue a single-use capability token after approval.

    Token is stored in Redis for revocation checking.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "shot_id": shot_id,
        "node_scope": node_scope,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=ttl)).timestamp(),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    # Register in Redis for revocation tracking
    await redis.set(f"cap_token:{token}", shot_id, ex=ttl)
    return token

async def verify_capability_token(
    redis: aioredis.Redis,
    token: str,
    secret: str,
) -> dict:
    """Verify and consume a capability token (single-use).

    Returns {valid, shot_id, node_scope, expires_at} or {valid: false, reason}.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return {"valid": False, "reason": "token_expired"}
    except jwt.InvalidTokenError:
        return {"valid": False, "reason": "invalid_token"}

    # Check revocation in Redis
    key = f"cap_token:{token}"
    stored = await redis.get(key)
    if stored is None:
        return {"valid": False, "reason": "token_revoked_or_consumed"}

    # Single-use: delete the key after successful verification
    await redis.delete(key)

    return {
        "valid": True,
        "shot_id": payload["shot_id"],
        "node_scope": payload["node_scope"],
        "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat(),
    }
```

### Pattern 3: Shadow Mode as arq Background Task
**What:** After every human review decision, enqueue an arq task that runs scoring and writes to `shadow_scores` table.
**When to use:** Post-review hook in the approval flow.
**Example:**
```python
# Source: extends pattern from app/workers/tasks.py process_node_completion
async def record_shadow_score(ctx: dict, shot_card_id: int, human_decision: str) -> dict:
    """Run scoring bus on a reviewed Shot Card and record shadow score.

    Runs as arq background task after every human review decision.
    Does not affect the actual review outcome.
    """
    from app.core.database import async_session_factory
    from app.models.shot_card import ShotCard
    from app.services.scoring_bus import get_scoring_bus
    from app.models.shadow_score import ShadowScore

    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)
        if not shot_card:
            return {"status": "error", "reason": "shot_card_not_found"}

        bus = get_scoring_bus()
        score_vector = await bus.score(shot_card)

        shadow = ShadowScore(
            shot_card_id=shot_card_id,
            shot_id=shot_card.shot_id,
            score_vector=score_vector.model_dump(),
            human_decision=human_decision,
        )
        session.add(shadow)
        await session.commit()

    return {"status": "recorded", "shot_card_id": shot_card_id}
```

### Pattern 4: In-Memory ModelRegistry
**What:** Simple dict-backed registry returning `model_unavailable` for all queries.
**When to use:** AI-03 model registry placeholder.
**Example:**
```python
# Source: follows singleton pattern from app/core/policy.py get_policy_engine()
class ModelInfo(BaseModel):
    name: str
    version: str
    status: Literal["available", "model_unavailable"]

class ModelRegistry:
    """Phase 0 placeholder: returns model_unavailable for all queries."""
    def __init__(self):
        self._models: dict[str, ModelInfo] = {}

    def get_model(self, name: str) -> ModelInfo:
        return ModelInfo(name=name, version="0.0.0", status="model_unavailable")

    def list_models(self) -> list[ModelInfo]:
        return []

_registry: ModelRegistry | None = None

def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
```

### Anti-Patterns to Avoid
- **Don't make scoring bus synchronous:** The scoring bus MUST be async because future AI plugins will call external model APIs. Phase 0 NullScoringPlugin can be sync internally but the interface must be `async def score()`.
- **Don't skip shadow recording on null scores:** Even null scores from Phase 0 must be recorded -- this validates the recording pipeline works end-to-end before real AI models are plugged in.
- **Don't use PostgreSQL for feedback data:** CONTEXT.md explicitly says feedback goes to MinIO JSONL, not PostgreSQL. Phase 22 handles tiered storage.
- **Don't reuse jwt_secret for capability tokens:** `capability_token_secret` is a separate Settings field. Using the same secret would mean compromising one token type compromises both.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT token creation/validation | Custom HMAC signing | PyJWT `jwt.encode`/`jwt.decode` | Already installed, handles edge cases (exp, algorithm validation) |
| Single-use token enforcement | Custom flag in PostgreSQL | Redis SET + DEL (atomic) | Already proven in `consume_review_token` Lua pattern |
| Plugin registration | Custom plugin discovery | Settings list + manual registration | Simple and explicit for 1 plugin; complex discovery is over-engineering |
| MinIO JSONL writing | Raw HTTP S3 requests | minio Python client | Handles auth signing, retries, multipart upload edge cases |
| Score dimension validation | Custom dict validation | Pydantic ScoreVector model | Type safety, JSON serialization, API validation all free |

**Key insight:** Every component in this phase is a stub. The value is in getting the interfaces right, not the implementation. The scoring bus interface, the token format, the shadow score schema, and the A/B test data structure will all survive into Phase 1-4 AI integration unchanged -- only the plugin implementations change.

## Common Pitfalls

### Pitfall 1: Capability Token Not Single-Use
**What goes wrong:** Token is verified but not consumed, allowing replay attacks.
**Why it happens:** Forgetting to delete the Redis key after successful verification.
**How to avoid:** Follow the `consume_review_token` pattern -- atomic GET + DEL. The `verify_capability_token` function should delete the Redis key on success.
**Warning signs:** Multiple downstream executions from a single approval.

### Pitfall 2: Shadow Score Table Missing from Alembic Migration
**What goes wrong:** Code references `shadow_scores` table but no migration creates it.
**Why it happens:** The table is new and easy to overlook in the migration file.
**How to avoid:** Create a single Alembic migration `002_shadow_and_ab_tables.py` that creates BOTH `shadow_scores` and `ab_test_pairs` tables. Verify with `alembic upgrade head`.
**Warning signs:** Import errors or runtime "relation does not exist" errors.

### Pitfall 3: Scoring Bus Called Synchronously from Async Context
**What goes wrong:** Scoring bus `score()` method blocks the event loop when future AI plugins make HTTP calls.
**Why it happens:** Making the interface synchronous because Phase 0 returns immediately.
**How to avoid:** Always define `score()` as `async def` even though NullScoringPlugin returns immediately. Future plugins WILL be async.
**Warning signs:** Event loop blocking when real AI scoring plugins are added in Phase 1.

### Pitfall 4: Feedback Writing Blocks Review Flow
**What goes wrong:** MinIO write happens inline during the review approval, blocking the response.
**Why it happens:** Writing to MinIO synchronously instead of delegating to arq.
**How to avoid:** Always enqueue feedback writing as an arq background task. The review response returns immediately; feedback is written asynchronously.
**Warning signs:** Slow review approval responses when MinIO is slow or unavailable.

### Pitfall 5: A/B Test Batch_id Collision
**What goes wrong:** Two batches get the same batch_id, corrupting paired records.
**Why it happens:** Using a simple counter or timestamp for batch_id.
**How to avoid:** Use UUID4 for batch_id. The A/B test endpoint generates `batch_id = str(uuid.uuid4())`.
**Warning signs:** Unexpected number of records when querying by batch_id.

## Code Examples

### ScoreVector Pydantic Model (for schemas.py)
```python
# Follows existing Pydantic model pattern from app/models/schemas.py
class ScoreVector(BaseModel):
    """Multi-dimensional scoring result from AI audit plugin."""
    aesthetics: float | None = None
    consistency: float | None = None
    compliance: float | None = None
    technical_quality: float | None = None
    audio_match: float | None = None
    plugin_name: str = ""
    plugin_version: str = ""
```

### shadow_scores Table Model
```python
# Follows pattern from app/models/audit_entry.py
class ShadowScore(Base):
    __tablename__ = "shadow_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shot_card_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shot_cards.id"), nullable=False)
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    score_vector: Mapped[dict] = mapped_column(JSONB, nullable=False)
    human_decision: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_shadow_shot_created", "shot_card_id", "created_at"),
        Index("ix_shadow_shot_id", "shot_id"),
    )
```

### ab_test_pairs Table Model
```python
class ABTestPair(Base):
    __tablename__ = "ab_test_pairs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ai_score: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    human_decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_ab_batch_created", "batch_id", "created_at"),
    )
```

### Capability Token Verification Endpoint
```python
# Follows pattern from app/api/v1/shot_cards.py
router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])

class TokenVerifyRequest(BaseModel):
    token: str

class TokenVerifyResponse(BaseModel):
    valid: bool
    shot_id: str | None = None
    node_scope: list[str] | None = None
    expires_at: str | None = None
    reason: str | None = None

@router.post("/verify", response_model=ApiResponse[TokenVerifyResponse])
async def verify_token(
    request: TokenVerifyRequest,
    settings: Settings = Depends(get_settings),
):
    redis = app.state.redis  # from FastAPI app state
    result = await verify_capability_token(redis, request.token, settings.capability_token_secret)
    return ApiResponse(data=TokenVerifyResponse(**result))
```

### A/B Test Batch Creation Endpoint
```python
# Follows pattern from app/api/v1/reviews.py submit_review
router = APIRouter(prefix="/api/v1/ab-tests", tags=["ab-tests"])

class ABTestCreateRequest(BaseModel):
    shot_ids: list[str] = Field(min_length=1, max_length=100)

class ABTestCreateResponse(BaseModel):
    batch_id: str
    total: int

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_ab_test(
    request: ABTestCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    batch_id = str(uuid.uuid4())
    for shot_id in request.shot_ids:
        pair = ABTestPair(batch_id=batch_id, shot_id=shot_id)
        db.add(pair)
    await db.commit()
    return ApiResponse(data=ABTestCreateResponse(batch_id=batch_id, total=len(request.shot_ids)))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| aioredis standalone | redis.asyncio (redis-py 5.x) | redis-py 4.2+ | Use `import redis.asyncio as aioredis` pattern already in codebase |
| SQLite | PostgreSQL + TimescaleDB | Phase 15 | All new tables use JSONB, BigInteger, PostgreSQL-specific indexes |
| Celery | arq | Phase 01 | All background tasks use arq `functions` list + `WorkerSettings` |
| python-jose | PyJWT | Phase 15 | PyJWT >= 2.11.0 required for CVE fix, already installed |

**Deprecated/outdated:**
- aioredis: Merged into redis-py. Do NOT install separately.
- python-jose: Maintenance questionable. PyJWT is the reference implementation.

## Open Questions

1. **MinIO client availability**
   - What we know: `minio` package is NOT currently installed in the environment.
   - What's unclear: Whether Phase 15's Docker Compose expansion (15-02-PLAN, not yet executed) will add it.
   - Recommendation: Add `minio` to requirements.txt and install during implementation. The feedback writer is a stub -- if MinIO is unavailable at implementation time, the arq task can log the feedback data instead and write to MinIO when the container is available.

2. **Hook point for shadow mode trigger**
   - What we know: Shadow mode must trigger "after every human review decision." The review flow goes through `transition_state()` in `state_machine.py`.
   - What's unclear: Whether to hook into `transition_state()` (which handles V1 Review model) or the future Shot Card-specific approval flow.
   - Recommendation: Create the arq task `record_shadow_score` and register it in `WorkerSettings.functions`. The integration point should be added where Shot Card approval/rejection happens -- likely the Phase 20 desktop workbench approval action. For Phase 19, provide a manual trigger via the A/B test endpoint to validate the shadow recording works.

3. **Capability token `node_scope` source**
   - What we know: CONTEXT.md says `node_scope` is a "flat list of authorized node IDs." The ShotCard model has `visual_bundle` and `audio_bundle` which contain node references.
   - What's unclear: Exactly which node IDs should be authorized. This depends on the OpenClaw DAG topology which is external.
   - Recommendation: For Phase 19, accept `node_scope` as a parameter during token issuance. The caller (approval flow) determines which nodes are downstream. The token just carries and verifies the scope.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | shadow_scores, ab_test_pairs tables | Not verified | -- | In-memory SQLite for tests (conftest pattern) |
| Redis | Token revocation, arq tasks | In Docker | 7.x (alpine) | -- |
| PyJWT | Capability tokens | Yes | 2.12.1 | -- |
| minio | Feedback cold storage | No | -- | Log feedback to structlog as stub |
| asyncpg | PostgreSQL driver | Yes | 0.31.0 | -- |
| pytest | Test runner | Yes | 9.0.3 | -- |
| pytest-asyncio | Async tests | Yes | 1.3.0 | -- |
| alembic | Migration for new tables | Yes | installed | -- |

**Missing dependencies with no fallback:**
- None that block implementation. MinIO client needs installation but feedback writing can be stubbed.

**Missing dependencies with fallback:**
- minio Python client: Not installed. Install via `pip install minio`. If MinIO service is unavailable, the feedback writer task logs feedback data as structured JSON via structlog and returns success.

## Sources

### Primary (HIGH confidence)
- Codebase direct inspection: `app/core/auth.py` (JWT patterns, Redis token patterns), `app/core/config.py` (Settings with capability_token_secret), `app/models/shot_card.py` (ShotCard model with RoutingDecision.AI_AUDIT), `app/services/checkpoint_manager.py` (Redis TTL patterns), `app/workers/tasks.py` (arq worker patterns), `app/models/audit_entry.py` (SQLAlchemy model patterns), `alembic/versions/001_initial_v2_schema.py` (migration patterns)
- PyPI verified: PyJWT 2.12.1, SQLAlchemy 2.0.49, Pydantic 2.13.3, redis-py 5.3.1, arq 0.28.0, asyncpg 0.31.0

### Secondary (MEDIUM confidence)
- V2 Architecture document (`.planning/research/V2-ARCHITECTURE.md`) -- AI audit window design specification
- CONTEXT.md locked decisions -- authoritative user decisions

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or PyPI.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed except minio, versions verified via pip show
- Architecture: HIGH -- follows established codebase patterns (service, worker, model, API route)
- Pitfalls: HIGH -- identified from direct codebase analysis of existing patterns and failure modes

**Research date:** 2026-05-16
**Valid until:** 2026-06-16 (stable -- no fast-moving dependencies)
