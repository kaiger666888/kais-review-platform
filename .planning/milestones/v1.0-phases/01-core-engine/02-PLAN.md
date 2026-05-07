---
phase: 01-core-engine
plan: 02
type: execute
wave: 2
depends_on:
  - 01
files_modified:
  - app/core/auth.py
  - app/core/state_machine.py
  - app/api/__init__.py
  - app/api/v1/__init__.py
  - app/api/v1/auth.py
autonomous: true
requirements:
  - AUTH-01
  - AUTH-02
  - AUTH-03
  - AUTH-04
  - SM-01
  - SM-02
  - SM-03
  - SM-04

must_haves:
  truths:
    - "API key can be exchanged for a short-lived JWT token (15min expiry)"
    - "JWT-protected endpoints reject requests without valid token (401)"
    - "One-time review tokens are 32+ chars, stored in Redis with TTL, and invalidated after single use"
    - "State transitions follow the 4-state graph: PENDING -> POLICY_EVAL -> APPROVING -> COMPLETE"
    - "Invalid transitions are rejected with clear error messages"
    - "Concurrent state transitions are detected via optimistic locking (409 Conflict)"
    - "Reject/escalate/expire transitions are available from non-terminal states"
  artifacts:
    - path: "app/core/auth.py"
      provides: "JWT creation/validation, one-time token creation/consumption, FastAPI auth dependencies"
      exports: ["create_jwt", "require_jwt", "get_current_client", "create_review_token", "consume_review_token"]
    - path: "app/core/state_machine.py"
      provides: "4-state enum, transition map, optimistic locking state transitions"
      exports: ["ReviewState", "Disposition", "TRANSITIONS", "transition_state", "InvalidTransitionError", "StateConflictError"]
    - path: "app/api/v1/auth.py"
      provides: "POST /api/v1/auth/token endpoint"
      exports: ["router"]
  key_links:
    - from: "app/api/v1/auth.py"
      to: "app/core/auth.py"
      via: "import create_jwt, validate JWT logic"
      pattern: "from app\\.core\\.auth import"
    - from: "app/core/auth.py"
      to: "app/core/config.py"
      via: "Settings.jwt_secret, Settings.api_key"
      pattern: "from app\\.core\\.config import"
    - from: "app/core/state_machine.py"
      to: "app/models/schema.py"
      via: "Review model for UPDATE with optimistic locking"
      pattern: "from app\\.models\\.schema import.*Review"
---

<objective>
Implement the authentication layer (JWT + one-time tokens) and the 4-state checkpoint state machine with optimistic locking. Wire the auth token endpoint.

Purpose: Auth protects all API endpoints. The state machine governs every review lifecycle transition. Both are required before the Review API and Policy Engine can function.

Output: Working JWT auth with one-time tokens, state machine that validates transitions with optimistic locking, and POST /api/v1/auth/token endpoint.
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

<interfaces>
<!-- From Plan 01: Foundation types and contracts executor needs -->

From app/core/config.py:
```python
class Settings(BaseSettings):
    api_key: str
    jwt_secret: str
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite+aiosqlite:///./data/review.db"
    log_level: str = "INFO"

def get_settings() -> Settings: ...
```

From app/core/database.py:
```python
engine: AsyncEngine
async_session_factory: async_sessionmaker[AsyncSession]
async def get_db() -> AsyncGenerator[AsyncSession, None]: ...
```

From app/models/schema.py:
```python
class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int]  # primary key
    state: Mapped[str]  # default "PENDING"
    version: Mapped[int]  # default 1
    # ... other columns

class AuditEntry(Base):
    __tablename__ = "audit_entries"
    # ... columns

def create_tables(conn): ...
```

From app/core/audit.py:
```python
class AuditLogger:
    async def log(self, session, review_id, action, actor, ...) -> AuditEntry: ...

async def append_audit(session, review_id, action, actor, **kwargs) -> AuditEntry: ...
```

From app/models/schemas.py:
```python
class ReviewState(str, Enum):
    PENDING = "PENDING"
    POLICY_EVAL = "POLICY_EVAL"
    APPROVING = "APPROVING"
    COMPLETE = "COMPLETE"

class Disposition(str, Enum):
    AUTO = "AUTO"
    HUMAN = "HUMAN"
    AI_AUDIT = "AI_AUDIT"
    BLOCK = "BLOCK"

class TokenRequest(BaseModel):
    api_key: str
    client_id: str
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement JWT auth and one-time review tokens</name>
  <files>app/core/auth.py, app/api/__init__.py, app/api/v1/__init__.py, app/api/v1/auth.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-RESEARCH.md (Pattern 3: Redis One-Time Token, JWT Auth Dependency code examples)
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: static API key -> JWT, Redis TTL for one-time tokens)
    - app/core/config.py (Settings class with jwt_secret, api_key)
    - app/core/database.py (get_db dependency)
    - app/main.py (get_redis dependency)
  </read_first>
  <action>
1. Create `app/core/auth.py`:

   **JWT functions:**
   - `create_jwt(client_id: str, jwt_secret: str, expires_minutes: int = 15) -> str`:
     - Payload: `{"client": client_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes), "iat": datetime.now(timezone.utc)}`
     - Encode with `jwt.encode(payload, jwt_secret, algorithm="HS256")`
     - Use `import jwt` (PyJWT)

   - `decode_jwt(token: str, jwt_secret: str) -> dict`:
     - `jwt.decode(token, jwt_secret, algorithms=["HS256"])`
     - Raise `AuthenticationError` on ExpiredSignatureError or InvalidTokenError

   **FastAPI auth dependencies:**
   - `security = HTTPBearer()`
   - `async def require_jwt(credentials: HTTPAuthorizationCredentials = Depends(security), settings: Settings = Depends(get_settings)) -> dict`:
     - Decode JWT, return payload dict
     - Raise HTTPException(401, "Token expired") on ExpiredSignatureError
     - Raise HTTPException(401, "Invalid token") on InvalidTokenError
   - `async def get_current_client(payload: dict = Depends(require_jwt)) -> str`:
     - Return `payload["client"]`

   **One-time review tokens:**
   - `LUA_CONSUME_TOKEN` string constant with Redis Lua script:
     ```python
     LUA_CONSUME_TOKEN = """
     if redis.call("GET", KEYS[1]) then
         local val = redis.call("GET", KEYS[1])
         redis.call("DEL", KEYS[1])
         return val
     else
         return nil
     end
     """
     ```
   - `async def create_review_token(redis: aioredis.Redis, review_id: int, ttl: int = 259200) -> str`:
     - Generate token: `secrets.token_urlsafe(32)`
     - Key: `f"review_token:{token}"`
     - `await redis.set(key, str(review_id), ex=ttl)`
     - Return token string
   - `async def consume_review_token(redis: aioredis.Redis, token: str) -> str | None`:
     - Register script: `consume = redis.register_script(LUA_CONSUME_TOKEN)`
     - Execute: `result = await consume(keys=[f"review_token:{token}"])`
     - Return result (string review_id or None)
   - Custom exception `class AuthenticationError(Exception): pass`

2. Create `app/api/__init__.py` and `app/api/v1/__init__.py` as empty files.

3. Create `app/api/v1/auth.py`:
   - `router = APIRouter(prefix="/api/v1/auth", tags=["auth"])`
   - `POST /token` endpoint:
     - Accept `TokenRequest` body (api_key, client_id)
     - Validate api_key matches `settings.api_key`, raise HTTPException(401, "Invalid API key") if not
     - Generate JWT: `create_jwt(request.client_id, settings.jwt_secret)`
     - Return `{"data": {"access_token": token, "token_type": "bearer", "expires_in": 900}}`
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.core.auth import create_jwt, decode_jwt, LUA_CONSUME_TOKEN, create_review_token, AuthenticationError
import jwt as pyjwt

# Test JWT creation and validation
token = create_jwt('test-client', 'test-secret-key-here-at-least-32', expires_minutes=15)
assert isinstance(token, str), 'JWT must be a string'
payload = decode_jwt(token, 'test-secret-key-here-at-least-32')
assert payload['client'] == 'test-client', 'Client ID must be in payload'
assert 'exp' in payload, 'Payload must have expiry'

# Test expired token
import time
expired_token = create_jwt('test', 'test-secret-key-here-at-least-32', expires_minutes=0)
# Manually create an already-expired token
from datetime import datetime, timezone, timedelta
import jwt
expired = jwt.encode({'client': 'test', 'exp': datetime.now(timezone.utc) - timedelta(seconds=1)}, 'test-secret-key-here-at-least-32', algorithm='HS256')
try:
    decode_jwt(expired, 'test-secret-key-here-at-least-32')
    assert False, 'Should raise error for expired token'
except (AuthenticationError, Exception):
    print('Expired token correctly rejected')

# Test Lua script exists
assert 'GET' in LUA_CONSUME_TOKEN and 'DEL' in LUA_CONSUME_TOKEN, 'Lua script must use GET and DEL'

# Test token length
import secrets
token_val = secrets.token_urlsafe(32)
assert len(token_val) >= 32, f'Token must be at least 32 chars, got {len(token_val)}'

print('Auth module tests passed')
"</automated>
  </verify>
  <done>
    - create_jwt produces valid HS256 JWT with 15min expiry and client claim
    - decode_jwt validates and returns payload
    - require_jwt FastAPI dependency extracts and validates Bearer token
    - One-time tokens are 43+ chars (token_urlsafe(32) produces base64)
    - Lua script performs atomic GET+DEL on Redis
    - POST /api/v1/auth/token exchanges API key for JWT
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement 4-state checkpoint state machine with optimistic locking</name>
  <files>app/core/state_machine.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: 4-state enum PENDING/POLICY_EVAL/APPROVING/COMPLETE, reject/escalate/expire transitions)
    - .planning/phases/01-core-engine/01-RESEARCH.md (Pattern 2: Optimistic Locking)
    - .planning/research/PITFALLS.md (Pitfall 3: State Machine Race Conditions)
    - app/models/schema.py (Review model with state, version columns)
    - app/core/audit.py (append_audit for transition logging)
  </read_first>
  <action>
1. Create `app/core/state_machine.py`:

   **Exceptions:**
   ```python
   class StateMachineError(Exception): pass
   class InvalidTransitionError(StateMachineError): pass
   class StateConflictError(StateMachineError): pass
   class TerminalStateError(StateMachineError): pass
   ```

   **Note on ReviewState/Disposition enums:** Move these from `app/models/schemas.py` to this file and re-export from schemas.py, OR import from schemas.py. Use the ones already defined in `app/models/schemas.py` (ReviewState and Disposition). Import them here.

   **Transition map:**
   ```python
   # Define ALL valid (from_state, to_state) pairs
   VALID_TRANSITIONS: set[tuple[ReviewState, ReviewState]] = {
       # Normal flow
       (ReviewState.PENDING, ReviewState.POLICY_EVAL),
       (ReviewState.POLICY_EVAL, ReviewState.APPROVING),      # HUMAN route
       (ReviewState.POLICY_EVAL, ReviewState.COMPLETE),        # AUTO or BLOCK route
       (ReviewState.APPROVING, ReviewState.COMPLETE),          # Human approves
       # Reject from any non-terminal state
       (ReviewState.POLICY_EVAL, ReviewState.COMPLETE),        # Already in set (BLOCK)
       (ReviewState.APPROVING, ReviewState.COMPLETE),          # Already in set (reject)
       # Escalate
       (ReviewState.APPROVING, ReviewState.PENDING),           # Escalate back to queue
       # Expire
       (ReviewState.APPROVING, ReviewState.POLICY_EVAL),       # Timeout re-eval
   }
   ```
   Actually, since sets deduplicate, simplify. Also need to handle reject as a transition to COMPLETE with a rejection disposition. The key insight: COMPLETE is the terminal state for BOTH approved and rejected reviews. The disposition field (AUTO/HUMAN/AI_AUDIT/BLOCK) and the action (approve/reject) in the audit log distinguish outcomes.

   Define the transition map clearly:
   ```python
   VALID_TRANSITIONS: dict[ReviewState, set[ReviewState]] = {
       ReviewState.PENDING: {ReviewState.POLICY_EVAL},
       ReviewState.POLICY_EVAL: {ReviewState.APPROVING, ReviewState.COMPLETE},
       ReviewState.APPROVING: {ReviewState.COMPLETE, ReviewState.PENDING, ReviewState.POLICY_EVAL},
       ReviewState.COMPLETE: set(),  # Terminal state
   }
   ```

   **Core transition function:**
   ```python
   async def transition_state(
       session: AsyncSession,
       review_id: int,
       from_state: ReviewState,
       to_state: ReviewState,
       expected_version: int,
       actor: str,
       action: str | None = None,
       payload: dict | None = None,
   ) -> Review:
   ```
   Implementation:
   a. Validate `to_state in VALID_TRANSITIONS.get(from_state, set())`. If not, raise `InvalidTransitionError` with message `"Invalid transition: {from_state.value} -> {to_state.value}"`.
   b. If `from_state == ReviewState.COMPLETE`, raise `TerminalStateError("Cannot transition from terminal state COMPLETE")`.
   c. Execute optimistic locking UPDATE:
      ```python
      stmt = (
          update(Review)
          .where(
              Review.id == review_id,
              Review.version == expected_version,
              Review.state == from_state.value,
          )
          .values(
              state=to_state.value,
              version=expected_version + 1,
              updated_at=func.now(),
          )
      )
      result = await session.execute(stmt)
      ```
   d. If `result.rowcount == 0`: raise `StateConflictError("State conflict: review was modified by another request or version mismatch")`.
   e. Commit the UPDATE.
   f. Append audit entry: `await append_audit(session, review_id=review_id, action=action or "transition", actor=actor, from_state=from_state.value, to_state=to_state.value, payload=payload)`.
   g. Refresh and return the Review object.

   **Helper functions:**
   - `def validate_transition(from_state: ReviewState, to_state: ReviewState) -> bool`: Check transition map, return bool.
   - `def get_allowed_transitions(state: ReviewState) -> set[ReviewState]`: Return valid next states.
   - `def is_terminal(state: ReviewState) -> bool`: Return `state == ReviewState.COMPLETE`.
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.core.state_machine import (
    ReviewState, Disposition, VALID_TRANSITIONS,
    validate_transition, get_allowed_transitions, is_terminal,
    InvalidTransitionError, StateConflictError, TerminalStateError
)

# Verify 4 states
states = list(ReviewState)
assert len(states) == 4, f'Expected 4 states, got {len(states)}'
state_names = {s.value for s in states}
assert state_names == {'PENDING', 'POLICY_EVAL', 'APPROVING', 'COMPLETE'}, f'Wrong states: {state_names}'

# Verify dispositions
dispositions = {d.value for d in Disposition}
assert dispositions == {'AUTO', 'HUMAN', 'AI_AUDIT', 'BLOCK'}, f'Wrong dispositions: {dispositions}'

# Verify valid transitions
assert validate_transition(ReviewState.PENDING, ReviewState.POLICY_EVAL), 'PENDING->POLICY_EVAL must be valid'
assert validate_transition(ReviewState.POLICY_EVAL, ReviewState.APPROVING), 'POLICY_EVAL->APPROVING must be valid'
assert validate_transition(ReviewState.POLICY_EVAL, ReviewState.COMPLETE), 'POLICY_EVAL->COMPLETE must be valid (AUTO/BLOCK)'
assert validate_transition(ReviewState.APPROVING, ReviewState.COMPLETE), 'APPROVING->COMPLETE must be valid'
assert validate_transition(ReviewState.APPROVING, ReviewState.PENDING), 'APPROVING->PENDING must be valid (escalate)'
assert validate_transition(ReviewState.APPROVING, ReviewState.POLICY_EVAL), 'APPROVING->POLICY_EVAL must be valid (expire)'

# Verify invalid transitions
assert not validate_transition(ReviewState.COMPLETE, ReviewState.PENDING), 'COMPLETE->PENDING must be invalid'
assert not validate_transition(ReviewState.PENDING, ReviewState.COMPLETE), 'PENDING->COMPLETE must be invalid'
assert not validate_transition(ReviewState.PENDING, ReviewState.APPROVING), 'PENDING->APPROVING must be invalid'

# Verify terminal state
assert is_terminal(ReviewState.COMPLETE), 'COMPLETE must be terminal'
assert not is_terminal(ReviewState.PENDING), 'PENDING must not be terminal'
assert not is_terminal(ReviewState.APPROVING), 'APPROVING must not be terminal'

# Verify COMPLETE has no outgoing transitions
assert len(get_allowed_transitions(ReviewState.COMPLETE)) == 0, 'COMPLETE must have no outgoing transitions'

print('State machine validation passed')
"</automated>
  </verify>
  <done>
    - ReviewState enum has exactly 4 states: PENDING, POLICY_EVAL, APPROVING, COMPLETE
    - VALID_TRANSITIONS maps each state to its allowed next states
    - COMPLETE has no outgoing transitions (terminal state)
    - transition_state uses optimistic locking (UPDATE WHERE version=?)
    - transition_state raises StateConflictError when rowcount==0
    - transition_state raises InvalidTransitionError for invalid transitions
    - Every transition appends an audit entry
    - get_allowed_transitions, is_terminal, validate_transition helpers work correctly
  </done>
</task>

</tasks>

<verification>
1. `from app.core.auth import create_jwt, require_jwt, create_review_token, consume_review_token` succeeds
2. JWT token creation and validation works with HS256
3. One-time token Lua script performs atomic GET+DEL
4. `from app.core.state_machine import transition_state, ReviewState, VALID_TRANSITIONS` succeeds
5. State machine rejects invalid transitions (e.g., COMPLETE -> PENDING)
6. State machine accepts all valid transitions from the 4-state graph
7. POST /api/v1/auth/token exchanges API key for JWT
8. Invalid API key returns 401
</verification>

<success_criteria>
- JWT tokens created with 15min expiry, validated on protected routes
- One-time tokens are 43+ chars, stored in Redis with TTL, consumed atomically via Lua script
- 4-state graph enforced: PENDING -> POLICY_EVAL -> APPROVING -> COMPLETE
- Optimistic locking prevents concurrent state conflicts (409)
- Reject/escalate/expire transitions available from non-terminal states
- POST /api/v1/auth/token working with valid/invalid API key handling
</success_criteria>

<output>
After completion, create `.planning/phases/01-core-engine/02-SUMMARY.md`
</output>
