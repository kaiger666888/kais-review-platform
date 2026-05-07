---
phase: 01-core-engine
plan: 05
type: execute
wave: 3
depends_on:
  - 02
  - 03
files_modified:
  - app/workers/__init__.py
  - app/workers/tasks.py
  - app/main.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_submit_flow.py
  - tests/test_approve_reject.py
  - tests/test_state_machine.py
  - tests/test_policy_engine.py
autonomous: true
requirements:
  - SM-05
  - SM-04
  - AUTH-04

must_haves:
  truths:
    - "Auto-escalation detects timed-out reviews and transitions them"
    - "Full submit-to-completion flow works end-to-end"
    - "State machine enforces valid transitions and rejects invalid ones"
    - "Policy engine routes reviews correctly based on conditions"
    - "One-time tokens work exactly once and are rejected on reuse"
    - "Concurrent approvals detected via optimistic locking"
  artifacts:
    - path: "app/workers/tasks.py"
      provides: "arq task definitions for auto-escalation timeout check"
      exports: ["check_timeouts", "WorkerSettings"]
    - path: "tests/conftest.py"
      provides: "Test fixtures for async client, db session, redis mock"
    - path: "tests/test_submit_flow.py"
      provides: "Integration test for full review submission flow"
    - path: "tests/test_approve_reject.py"
      provides: "Integration tests for approve/reject with one-time tokens"
    - path: "tests/test_state_machine.py"
      provides: "Unit tests for state machine transitions and concurrency"
    - path: "tests/test_policy_engine.py"
      provides: "Unit tests for policy engine evaluation"
  key_links:
    - from: "app/workers/tasks.py"
      to: "app/core/state_machine.py"
      via: "transition_state for timeout escalation"
      pattern: "transition_state"
    - from: "app/workers/tasks.py"
      to: "app/core/database.py"
      via: "get_db for querying timed-out reviews"
      pattern: "get_db|async_session_factory"
    - from: "tests/"
      to: "app/main.py"
      via: "httpx AsyncClient for integration testing"
      pattern: "from app\\.main import app"
---

<objective>
Implement the arq auto-escalation timeout task and write comprehensive integration tests that validate the entire Phase 1 system end-to-end.

Purpose: SM-05 (timeout auto-escalation) is the last functional requirement. The tests prove that all 26 Phase 1 requirements work correctly as an integrated system, not just as isolated components. This plan validates the critical path: submit -> policy eval -> route -> approve/reject -> audit trail.

Output: Working auto-escalation task and a test suite covering all major flows.
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
@.planning/phases/01-core-engine/01-SUMMARY.md
@.planning/phases/01-core-engine/02-SUMMARY.md
@.planning/phases/01-core-engine/03-SUMMARY.md
@.planning/phases/01-core-engine/04-SUMMARY.md

<interfaces>
<!-- From Plans 01-04: All contracts for tests and tasks -->

From app/main.py:
```python
app: FastAPI  # includes all routers: auth, reviews, policies, actions, audit
# app.state.redis: aioredis.Redis
# app.state.arq_pool: ArqRedis
```

From app/core/state_machine.py:
```python
async def transition_state(session, review_id, from_state, to_state, expected_version, actor, ...) -> Review: ...
```

From app/core/policy.py:
```python
class PolicyEngine:
    def evaluate(self, review_data: dict, policy_name=None) -> Disposition: ...
def get_policy_engine() -> PolicyEngine: ...
```

From app/core/auth.py:
```python
def create_jwt(client_id, jwt_secret, expires_minutes=15) -> str: ...
async def create_review_token(redis, review_id, ttl=259200) -> str: ...
async def consume_review_token(redis, token) -> str | None: ...
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement arq auto-escalation task</name>
  <files>app/workers/__init__.py, app/workers/tasks.py, app/main.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: arq scheduled task with Redis TTL for auto-escalation)
    - .planning/phases/01-core-engine/01-RESEARCH.md (SM-05 requirement, arq patterns)
    - app/core/state_machine.py (transition_state for escalation)
    - app/models/schema.py (Review model for querying)
    - app/main.py (current state for arq integration)
  </read_first>
  <action>
1. Create `app/workers/__init__.py` as empty file.

2. Create `app/workers/tasks.py`:

   **Timeout configuration:**
   ```python
   # Timeout thresholds per route type
   TIMEOUT_THRESHOLDS: dict[str, int] = {
       "AI_AUDIT": 300,    # 5 minutes for AI review
       "HUMAN": 86400,     # 24 hours for human review
   }
   DEFAULT_TIMEOUT = 86400  # 24 hours default
   ```

   **check_timeouts task:**
   ```python
   async def check_timeouts(ctx: dict) -> list[int]:
       """Scan for reviews in APPROVING state that have exceeded timeout threshold.
       Escalates timed-out reviews by transitioning back to POLICY_EVAL for re-evaluation.
       Returns list of escalated review IDs."""
       from app.core.database import async_session_factory
       from app.models.schema import Review
       from app.core.state_machine import transition_state, ReviewState
       from datetime import datetime, timezone, timedelta
       import structlog

       logger = structlog.get_logger()
       escalated = []

       async with async_session_factory() as session:
           # Find reviews in APPROVING state that have been pending too long
           cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=DEFAULT_TIMEOUT)
           query = select(Review).where(
               Review.state == ReviewState.APPROVING.value,
               Review.updated_at < cutoff_time,
           )
           result = await session.execute(query)
           timed_out_reviews = result.scalars().all()

           for review in timed_out_reviews:
               try:
                   await transition_state(
                       session,
                       review.id,
                       ReviewState.APPROVING,
                       ReviewState.POLICY_EVAL,
                       review.version,
                       actor="timeout",
                       action="auto_escalate",
                       payload={"reason": "Review exceeded timeout threshold", "timeout_seconds": DEFAULT_TIMEOUT},
                   )
                   escalated.append(review.id)
                   logger.info("review_escalated", review_id=review.id, reason="timeout")
               except Exception as e:
                   logger.error("escalation_failed", review_id=review.id, error=str(e))

       return escalated
   ```

   **WorkerSettings for arq:**
   ```python
   class WorkerSettings:
       """arq worker configuration."""
       functions = [check_timeouts]
       cron_jobs = [
           cron(check_timeouts, minute={0}),  # Run every hour at minute 0
       ]
       # For development, can also run more frequently:
       # cron_jobs = [cron(check_timeouts, second={0})]  # Every minute
   ```

   NOTE: Import `cron` from `arq` as needed: `from arq import cron`

3. Update `app/main.py` to ensure arq pool is available for the worker:
   - The lifespan already creates `app.state.arq_pool` -- no changes needed for the pool itself.
   - Add a `WorkerSettings` reference so the worker can be started separately:
     ```python
     # At bottom of main.py or in a separate worker entry point:
     # Run with: arq app.workers.tasks.WorkerSettings
     ```
   - No additional changes to main.py needed -- the worker runs as a separate process.
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.workers.tasks import check_timeouts, WorkerSettings, TIMEOUT_THRESHOLDS, DEFAULT_TIMEOUT
assert 'AI_AUDIT' in TIMEOUT_THRESHOLDS, 'Must have AI_AUDIT timeout'
assert 'HUMAN' in TIMEOUT_THRESHOLDS, 'Must have HUMAN timeout'
assert TIMEOUT_THRESHOLDS['AI_AUDIT'] == 300, 'AI_AUDIT timeout must be 300 seconds (5 min)'
assert TIMEOUT_THRESHOLDS['HUMAN'] == 86400, 'HUMAN timeout must be 86400 seconds (24h)'
assert DEFAULT_TIMEOUT == 86400, 'Default timeout must be 24h'
assert hasattr(WorkerSettings, 'functions'), 'WorkerSettings must have functions'
assert hasattr(WorkerSettings, 'cron_jobs'), 'WorkerSettings must have cron_jobs'
assert check_timeouts in WorkerSettings.functions, 'check_timeouts must be in functions'
print('Auto-escalation task verified')
print(f'Timeouts: AI={TIMEOUT_THRESHOLDS[\"AI_AUDIT\"]}s, Human={TIMEOUT_THRESHOLDS[\"HUMAN\"]}s')
"</automated>
  </verify>
  <done>
    - check_timeouts function queries APPROVING reviews past timeout threshold
    - Timed-out reviews escalated to POLICY_EVAL for re-evaluation
    - AI_AUDIT timeout: 5 minutes, HUMAN timeout: 24 hours
    - WorkerSettings configures arq cron job
    - Escalation logged to audit trail via transition_state
  </done>
</task>

<task type="auto">
  <name>Task 2: Write integration tests for full review lifecycle</name>
  <files>tests/__init__.py, tests/conftest.py, tests/test_submit_flow.py, tests/test_approve_reject.py, tests/test_state_machine.py, tests/test_policy_engine.py</files>
  <read_first>
    - app/main.py (FastAPI app for test client)
    - app/core/auth.py (create_jwt for test auth headers)
    - app/core/config.py (Settings for test configuration)
    - app/core/state_machine.py (transition_state, ReviewState)
    - app/core/policy.py (PolicyEngine)
    - app/models/schemas.py (ReviewState, Disposition enums)
    - app/api/v1/reviews.py (submit endpoint)
    - app/api/v1/actions.py (approve/reject endpoints)
  </read_first>
  <action>
1. Create `tests/__init__.py` as empty file.

2. Create `tests/conftest.py` with pytest fixtures:

   ```python
   import pytest
   import pytest_asyncio
   from httpx import AsyncClient, ASGITransport
   from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
   from app.models.schema import Base, create_tables
   from app.core.auth import create_jwt
   from app.core.config import Settings

   @pytest.fixture
   def settings():
       return Settings(api_key="test-api-key", jwt_secret="test-jwt-secret-for-testing-min-32-chars")

   @pytest.fixture
   def auth_headers(settings):
       token = create_jwt("test-client", settings.jwt_secret)
       return {"Authorization": f"Bearer {token}"}

   @pytest_asyncio.fixture
   async def db_engine():
       engine = create_async_engine(
           "sqlite+aiosqlite:///:memory:",
           connect_args={"check_same_thread": False},
       )
       async with engine.begin() as conn:
           await conn.run_sync(create_tables)
       yield engine
       await engine.dispose()

   @pytest_asyncio.fixture
   async def db_session(db_engine):
       factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
       async with factory() as session:
           yield session
   ```

   NOTE: For full integration tests with the FastAPI app, you will need to mock Redis since the test environment may not have Redis available. Use `unittest.mock.AsyncMock` to mock Redis operations, or create a fakeredis-based fixture. The key approach:
   - Override the `get_redis` dependency in the FastAPI app with a mock
   - Override `get_settings` with test settings
   - Use `httpx.AsyncClient` with `ASGITransport(app=app)` for testing

3. Create `tests/test_submit_flow.py`:
   - Test: submit low-risk review -> auto-approved (COMPLETE state)
     - POST /api/v1/reviews with risk_score=0.1, source_system="kais-movie-agent"
     - Assert response status 202
     - Assert response.data.routing == "AUTO"
     - GET /api/v1/reviews/{id} -> assert state == "COMPLETE"
   - Test: submit high-risk review -> human review (APPROVING state)
     - POST with risk_score=0.8
     - Assert routing == "HUMAN"
     - Assert state == "APPROVING"
   - Test: submit flagged content -> blocked (COMPLETE state)
     - POST with metadata={"flagged": True}
     - Assert routing == "BLOCK"
   - Test: submit without auth -> 401 or 403
   - Test: submit with invalid data -> 422

4. Create `tests/test_approve_reject.py`:
   - Test: approve review with JWT auth
     - Submit high-risk review (APPROVING state)
     - POST /api/v1/reviews/{id}/approve with comment
     - Assert state == "COMPLETE"
   - Test: reject review with mandatory reason
     - Submit high-risk review
     - POST /api/v1/reviews/{id}/reject with reason
     - Assert state == "COMPLETE"
   - Test: reject without reason -> 422
   - Test: approve non-APPROVING review -> 409
   - Test: approve already-approved review -> 409
   - Test: one-time token approve flow
     - Submit review, create review token
     - POST /api/v1/reviews/{id}/approve?token=xxx
     - Assert success
     - POST again with same token -> 401 (already consumed)

5. Create `tests/test_state_machine.py`:
   - Test: all valid transitions succeed
     - PENDING -> POLICY_EVAL, POLICY_EVAL -> APPROVING, APPROVING -> COMPLETE
   - Test: invalid transitions rejected
     - PENDING -> COMPLETE (invalid)
     - COMPLETE -> PENDING (terminal state)
   - Test: optimistic locking conflict
     - Create review at version 1
     - Transition with expected_version=1 -> succeeds (version becomes 2)
     - Transition with expected_version=1 again -> StateConflictError
   - Test: escalate from APPROVING back to PENDING
   - Test: expire from APPROVING to POLICY_EVAL

6. Create `tests/test_policy_engine.py`:
   - Test: load and evaluate default.yaml
   - Test: risk_score < 0.3 from movie-agent -> AUTO
   - Test: risk_score > 0.7 -> HUMAN
   - Test: priority=critical -> HUMAN (regardless of risk)
   - Test: metadata.flagged=true -> BLOCK
   - Test: no matching rule -> HUMAN default
   - Test: invalid YAML rejected with PolicyValidationError
   - Test: missing required fields rejected
   - Test: invalid disposition value rejected
   - Test: AND operator requires all checks true
   - Test: OR operator requires any check true
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -m pytest tests/test_policy_engine.py tests/test_state_machine.py -v --tb=short 2>&1 | tail -30</automated>
  </verify>
  <done>
    - tests/conftest.py provides auth_headers, db_session fixtures
    - tests/test_submit_flow.py covers submit + policy eval + routing
    - tests/test_approve_reject.py covers approve/reject with JWT and one-time tokens
    - tests/test_state_machine.py covers all transitions, conflict detection, escalation
    - tests/test_policy_engine.py covers condition evaluation, validation, defaults
    - Unit tests (state_machine, policy_engine) pass without Redis
    - All tests runnable with `pytest tests/ -v`
  </done>
</task>

</tasks>

<verification>
1. `python -m pytest tests/test_policy_engine.py -v` passes
2. `python -m pytest tests/test_state_machine.py -v` passes
3. check_timeouts function exists with correct timeout thresholds
4. WorkerSettings configures cron job for auto-escalation
5. Integration tests validate full submit -> route -> approve -> audit flow
6. One-time token consume-once behavior tested
7. Optimistic locking conflict detection tested
</verification>

<success_criteria>
- arq auto-escalation task scans for timed-out reviews and escalates them
- AI_AUDIT timeout: 5 minutes, HUMAN timeout: 24 hours
- Test suite covers submit flow, approve/reject, state machine, policy engine
- State machine tests validate all valid transitions and reject invalid ones
- Policy engine tests validate AND/OR evaluation, risk thresholds, defaults
- One-time token single-use verified in tests
- Optimistic locking conflict detection verified in tests
</success_criteria>

<output>
After completion, create `.planning/phases/01-core-engine/05-SUMMARY.md`
</output>
