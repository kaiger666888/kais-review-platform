---
phase: 01-core-engine
plan: 04
type: execute
wave: 3
depends_on:
  - 02
  - 03
files_modified:
  - app/api/v1/reviews.py
  - app/api/v1/actions.py
  - app/api/v1/audit_api.py
  - app/main.py
autonomous: true
requirements:
  - REV-01
  - REV-02
  - REV-03
  - REV-04
  - REV-05
  - REV-06
  - REV-07
  - AUDT-04
  - AUDT-05

must_haves:
  truths:
    - "External systems can POST a review item and receive review_id with routing decision"
    - "Review submission includes type, content_ref, metadata, source_system, priority"
    - "Submitters receive immediate response with review_id and routing decision (202 Accepted)"
    - "Reviewers can approve items with optional comment"
    - "Reviewers can reject items with mandatory reason"
    - "Review status is queryable by ID"
    - "Reviews are listable with filters (status, type, source, date range) and cursor pagination"
    - "Audit history is queryable by review_id"
    - "Audit log supports filtered queries (date range, action type, actor)"
  artifacts:
    - path: "app/api/v1/reviews.py"
      provides: "POST /api/v1/reviews, GET /api/v1/reviews/{id}, GET /api/v1/reviews"
      exports: ["router"]
    - path: "app/api/v1/actions.py"
      provides: "POST /api/v1/reviews/{id}/approve, POST /api/v1/reviews/{id}/reject"
      exports: ["router"]
    - path: "app/api/v1/audit_api.py"
      provides: "GET /api/v1/audit/{review_id}, GET /api/v1/audit"
      exports: ["router"]
    - path: "app/main.py"
      provides: "Updated to include all API routers"
  key_links:
    - from: "app/api/v1/reviews.py"
      to: "app/core/policy.py"
      via: "evaluate_policy on review submission"
      pattern: "policy_engine\\.evaluate|evaluate_policy"
    - from: "app/api/v1/reviews.py"
      to: "app/core/state_machine.py"
      via: "transition_state during submit flow"
      pattern: "transition_state"
    - from: "app/api/v1/actions.py"
      to: "app/core/state_machine.py"
      via: "transition_state for approve/reject"
      pattern: "transition_state"
    - from: "app/api/v1/actions.py"
      to: "app/core/auth.py"
      via: "consume_review_token for one-time approval links"
      pattern: "consume_review_token"
    - from: "app/api/v1/audit_api.py"
      to: "app/models/schema.py"
      via: "AuditEntry queries"
      pattern: "AuditEntry|audit_entries"
---

<objective>
Wire the complete Review API: submit (with policy evaluation + state machine routing), approve/reject (with one-time token support), query by ID, list with filters + cursor pagination, and audit trail query endpoints. Register all routers in main.py.

Purpose: This is the culmination of Plans 01-03. The Review API is the external interface that connects all subsystems: auth gates access, policy engine routes submissions, state machine manages transitions, and audit trail records everything.

Output: Fully functional REST API testable via curl -- external systems can submit, approve, reject, query, and list reviews with full audit trail visibility.
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

<interfaces>
<!-- From Plans 01-03: All contracts the executor needs -->

From app/core/auth.py:
```python
def create_jwt(client_id: str, jwt_secret: str, expires_minutes: int = 15) -> str: ...
async def require_jwt(...) -> dict: ...
async def get_current_client(payload: dict = Depends(require_jwt)) -> str: ...
async def create_review_token(redis: aioredis.Redis, review_id: int, ttl: int = 259200) -> str: ...
async def consume_review_token(redis: aioredis.Redis, token: str) -> str | None: ...
```

From app/core/state_machine.py:
```python
class ReviewState(str, Enum):
    PENDING = "PENDING"
    POLICY_EVAL = "POLICY_EVAL"
    APPROVING = "APPROVING"
    COMPLETE = "COMPLETE"

async def transition_state(
    session: AsyncSession, review_id: int,
    from_state: ReviewState, to_state: ReviewState,
    expected_version: int, actor: str,
    action: str | None = None, payload: dict | None = None,
) -> Review: ...

def get_allowed_transitions(state: ReviewState) -> set[ReviewState]: ...
def is_terminal(state: ReviewState) -> bool: ...
```

From app/core/policy.py:
```python
class PolicyEngine:
    def evaluate(self, review_data: dict, policy_name: str | None = None) -> Disposition: ...
    def load_policy(self, name: str, yaml_content: str) -> dict: ...

def get_policy_engine() -> PolicyEngine: ...
```

From app/core/audit.py:
```python
async def append_audit(session, review_id, action, actor, **kwargs) -> AuditEntry: ...
```

From app/core/database.py:
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]: ...
```

From app/models/schema.py:
```python
class Review(Base):
    id, type, content_ref, metadata_json, source_system, priority, risk_score,
    state, disposition, version, created_at, updated_at

class AuditEntry(Base):
    id, review_id, action, actor, from_state, to_state, payload, prev_hash, own_hash, created_at
```

From app/models/schemas.py:
```python
class ReviewCreateRequest(BaseModel):  # type, content_ref, metadata, source_system, priority, risk_score
class ApproveRequest(BaseModel):  # comment: str | None
class RejectRequest(BaseModel):  # reason: str (min_length=1, max_length=500)
class ReviewResponse(BaseModel):  # id, type, content_ref, metadata, ...
class ReviewSubmitResponse(BaseModel):  # review_id, state, routing
class AuditEntryResponse(BaseModel):  # id, review_id, action, actor, ...
class ApiResponse[T](BaseModel):  # data, meta, error
class PaginatedResponse[T](BaseModel):  # items, next_cursor, has_more
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement review submission and query endpoints</name>
  <files>app/api/v1/reviews.py, app/main.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: {data, meta, error} envelope, cursor-based pagination)
    - .planning/phases/01-core-engine/01-RESEARCH.md (Complete Review Submission Flow, Cursor-Based Pagination code)
    - app/core/state_machine.py (transition_state, ReviewState)
    - app/core/policy.py (PolicyEngine.evaluate, get_policy_engine)
    - app/core/auth.py (require_jwt, get_current_client)
    - app/models/schema.py (Review model)
    - app/models/schemas.py (ReviewCreateRequest, ReviewResponse, etc.)
    - app/main.py (current state to add routers)
  </read_first>
  <action>
1. Create `app/api/v1/reviews.py`:

   ```python
   router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])
   ```

   **POST / -- Submit review (REV-01, REV-02, REV-03):**
   - Accept `ReviewCreateRequest` body
   - Require JWT auth via `Depends(get_current_client)`
   - Implementation:
     a. Create Review record in PENDING state:
        ```python
        review = Review(
            type=request.type,
            content_ref=request.content_ref,
            metadata_json=request.metadata,
            source_system=request.source_system,
            priority=request.priority,
            risk_score=request.risk_score,
            state=ReviewState.PENDING.value,
            disposition=None,
            version=1,
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)
        ```
     b. Transition PENDING -> POLICY_EVAL:
        ```python
        await transition_state(db, review.id, ReviewState.PENDING, ReviewState.POLICY_EVAL, 1, "system", action="policy_eval_start")
        ```
     c. Evaluate policy:
        ```python
        engine = get_policy_engine()
        review_data = {
            "type": request.type,
            "source_system": request.source_system,
            "priority": request.priority,
            "risk_score": request.risk_score or 0.5,
            "metadata": request.metadata or {},
        }
        disposition = engine.evaluate(review_data)
        ```
     d. Route based on disposition:
        - AUTO: `transition_state(db, review.id, ReviewState.POLICY_EVAL, ReviewState.COMPLETE, 2, "policy_engine", action="auto_approve", payload={"disposition": disposition.value})`
        - HUMAN: `transition_state(db, review.id, ReviewState.POLICY_EVAL, ReviewState.APPROVING, 2, "policy_engine", action="route_human", payload={"disposition": disposition.value})`
        - AI_AUDIT: Same as HUMAN for now (Phase 2 will add AI scoring)
        - BLOCK: `transition_state(db, review.id, ReviewState.POLICY_EVAL, ReviewState.COMPLETE, 2, "policy_engine", action="block", payload={"disposition": disposition.value})`
     e. Update review.disposition to disposition.value and commit
     f. Return 202 Accepted with envelope:
        ```python
        {
            "data": {
                "review_id": review.id,
                "state": review.state,
                "routing": disposition.value,
            },
            "meta": {"request_id": "..."}
        }
        ```

   **GET /{review_id} -- Query review status (REV-06):**
   - Require JWT auth
   - Query Review by id, return 404 if not found
   - Return `ApiResponse[ReviewResponse]` with full review data

   **GET / -- List reviews with filters and pagination (REV-07):**
   - Require JWT auth
   - Query parameters:
     - `status: str | None` (filter by ReviewState value)
     - `type: str | None` (filter by review type)
     - `source: str | None` (filter by source_system)
     - `priority: str | None` (filter by priority)
     - `cursor: int | None = None` (id-based cursor, reviews with id < cursor)
     - `limit: int = 50` (page size, max 100)
   - Implementation:
     ```python
     query = select(Review).order_by(Review.id.desc()).limit(limit + 1)
     if cursor:
         query = query.where(Review.id < cursor)
     if status:
         query = query.where(Review.state == status)
     if type:
         query = query.where(Review.type == type)
     if source:
         query = query.where(Review.source_system == source)
     if priority:
         query = query.where(Review.priority == priority)
     ```
   - Extract results, compute has_more, next_cursor
   - Return `ApiResponse[PaginatedResponse[ReviewResponse]]`

2. Update `app/main.py` to include all routers:
   - Import routers:
     ```python
     from app.api.v1.auth import router as auth_router
     from app.api.v1.reviews import router as reviews_router
     from app.api.v1.policies import router as policies_router
     ```
   - Include routers:
     ```python
     app.include_router(auth_router)
     app.include_router(reviews_router)
     app.include_router(policies_router)
     ```
   - Also load default policies in lifespan after DB init:
     ```python
     from app.core.policy import get_policy_engine
     engine = get_policy_engine()
     engine.load_from_directory("app/policies")
     ```
   - NOTE: actions_router and audit_api_router will be added in Task 2. For now, include what exists.
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.api.v1.reviews import router
assert router.prefix == '/api/v1/reviews', f'Wrong prefix: {router.prefix}'
routes = {r.name: list(r.methods) for r in router.routes if hasattr(r, 'methods')}
print(f'Review routes: {routes}')
assert 'submit_review' in routes or any('post' in str(m).lower() for m in routes.values()), 'Must have POST route'
assert 'list_reviews' in routes or any('get' in str(m).lower() for m in routes.values()), 'Must have GET list route'
print('Review API structure verified')
"</automated>
  </verify>
  <done>
    - POST /api/v1/reviews creates review, evaluates policy, transitions state, returns 202
    - GET /api/v1/reviews/{id} returns review with 404 for missing
    - GET /api/v1/reviews returns paginated list with status/type/source/priority filters
    - Cursor-based pagination works with id-based cursor
    - All endpoints use {data, meta, error} envelope
    - All endpoints require JWT authentication
    - main.py includes auth, reviews, and policies routers
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement approve/reject actions and audit query endpoints</name>
  <files>app/api/v1/actions.py, app/api/v1/audit_api.py, app/main.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: one-time tokens for approval)
    - app/core/auth.py (consume_review_token, require_jwt, get_current_client)
    - app/core/state_machine.py (transition_state, ReviewState, StateConflictError, InvalidTransitionError)
    - app/models/schema.py (Review, AuditEntry models)
    - app/models/schemas.py (ApproveRequest, RejectRequest, AuditEntryResponse)
    - app/main.py (to add new routers)
  </read_first>
  <action>
1. Create `app/api/v1/actions.py`:

   ```python
   router = APIRouter(prefix="/api/v1/reviews", tags=["actions"])
   ```

   **POST /{review_id}/approve -- Approve review (REV-04):**
   - Accept `ApproveRequest` body (comment is optional)
   - Auth options (both supported):
     a. JWT auth: `client = Depends(get_current_client)` -- standard API approval
     b. One-time token: query parameter `?token=xxx` -- deep link approval
   - Implementation:
     a. If `token` query param provided:
        - `review_id_from_token = await consume_review_token(redis, token)`
        - If None (already consumed or expired), return 401 "Token invalid or already used"
        - If `int(review_id_from_token) != review_id`, return 403 "Token does not match review"
        - actor = "token_holder"
     b. Else use JWT client as actor: `f"client:{client}"`
     c. Fetch review by id. If not found, return 404.
     d. Check review.state is APPROVING. If not, return 409 "Review is not in APPROVING state, current state: {review.state}"
     e. Transition:
        ```python
        await transition_state(
            db, review.id,
            ReviewState.APPROVING, ReviewState.COMPLETE,
            review.version, actor,
            action="approve",
            payload={"comment": request.comment},
        )
        ```
     f. Refresh review, return 200 with `ApiResponse[ReviewResponse]`

   **POST /{review_id}/reject -- Reject review (REV-05):**
   - Accept `RejectRequest` body (reason is MANDATORY, min_length=1)
   - Same auth pattern as approve (JWT or one-time token)
   - Implementation:
     a. Same token handling as approve
     b. Fetch review, check state is APPROVING
     c. Transition APPROVING -> COMPLETE with action="reject":
        ```python
        await transition_state(
            db, review.id,
            ReviewState.APPROVING, ReviewState.COMPLETE,
            review.version, actor,
            action="reject",
            payload={"reason": request.reason},
        )
        ```
     d. Return 200 with `ApiResponse[ReviewResponse]`

   **Error handling for both endpoints:**
   - `StateConflictError` -> 409 Conflict "State conflict: review was modified concurrently"
   - `InvalidTransitionError` -> 409 "Invalid state transition"
   - Token already consumed -> 401 "Token invalid or already used"

2. Create `app/api/v1/audit_api.py`:

   ```python
   router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
   ```

   **GET /{review_id} -- Audit history for a review (AUDT-04):**
   - Require JWT auth
   - Query all AuditEntry records where `review_id == review_id`, ordered by `created_at ASC`
   - Return `ApiResponse[list[AuditEntryResponse]]`
   - If no entries found, return 200 with empty list (not 404 -- a review may not have audit entries yet)

   **GET / -- Audit log with filters (AUDT-05):**
   - Require JWT auth
   - Query parameters:
     - `action: str | None` (filter by action type)
     - `actor: str | None` (filter by actor)
     - `start_date: str | None` (ISO 8601 date, filter created_at >= start_date)
     - `end_date: str | None` (ISO 8601 date, filter created_at <= end_date)
     - `cursor: int | None` (id-based cursor, entries with id < cursor)
     - `limit: int = 50` (max 100)
   - Build query:
     ```python
     query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit + 1)
     if cursor:
         query = query.where(AuditEntry.id < cursor)
     if action:
         query = query.where(AuditEntry.action == action)
     if actor:
         query = query.where(AuditEntry.actor == actor)
     if start_date:
         query = query.where(AuditEntry.created_at >= datetime.fromisoformat(start_date))
     if end_date:
         query = query.where(AuditEntry.created_at <= datetime.fromisoformat(end_date))
     ```
   - Return `ApiResponse[PaginatedResponse[AuditEntryResponse]]`

3. Update `app/main.py` to include the new routers:
   ```python
   from app.api.v1.actions import router as actions_router
   from app.api.v1.audit_api import router as audit_router

   app.include_router(actions_router)
   app.include_router(audit_router)
   ```
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.api.v1.actions import router as actions_router
from app.api.v1.audit_api import router as audit_router

# Verify actions routes
assert actions_router.prefix == '/api/v1/reviews', f'Wrong actions prefix: {actions_router.prefix}'
action_routes = [(r.name, list(r.methods)) for r in actions_router.routes if hasattr(r, 'methods')]
print(f'Action routes: {action_routes}')
route_names = [name for name, _ in action_routes]
assert any('approve' in str(name) for name in route_names), 'Must have approve route'
assert any('reject' in str(name) for name in route_names), 'Must have reject route'

# Verify audit routes
assert audit_router.prefix == '/api/v1/audit', f'Wrong audit prefix: {audit_router.prefix}'
audit_routes = [(r.name, list(r.methods)) for r in audit_router.routes if hasattr(r, 'methods')]
print(f'Audit routes: {audit_routes}')

# Verify main.py has all routers
from app.main import app
all_routes = [r.path for r in app.routes if hasattr(r, 'path')]
print(f'All registered routes: {[r for r in all_routes if \"/api/v1\" in r]}')
assert any('/api/v1/auth' in r for r in all_routes), 'auth router must be registered'
assert any('/api/v1/reviews' in r for r in all_routes), 'reviews router must be registered'
assert any('/api/v1/audit' in r for r in all_routes), 'audit router must be registered'
assert any('/api/v1/policies' in r for r in all_routes), 'policies router must be registered'
print('All routers verified in main.py')
"</automated>
  </verify>
  <done>
    - POST /api/v1/reviews/{id}/approve works with JWT or one-time token
    - POST /api/v1/reviews/{id}/reject requires mandatory reason, works with JWT or one-time token
    - One-time tokens are consumed atomically (single use)
    - Approve/reject check review is in APPROVING state
    - StateConflictError returns 409
    - GET /api/v1/audit/{review_id} returns chronological audit entries
    - GET /api/v1/audit returns filtered paginated audit log
    - All routers registered in main.py
    - main.py loads default policies on startup
  </done>
</task>

</tasks>

<verification>
1. All routers registered in main.py (auth, reviews, policies, actions, audit)
2. POST /api/v1/reviews creates review, evaluates policy, routes to correct state
3. GET /api/v1/reviews/{id} returns review with 404 for missing
4. GET /api/v1/reviews returns paginated list with filters
5. POST /api/v1/reviews/{id}/approve transitions APPROVING -> COMPLETE
6. POST /api/v1/reviews/{id}/reject transitions APPROVING -> COMPLETE with reason
7. One-time tokens work for approve/reject
8. GET /api/v1/audit/{review_id} returns audit history
9. GET /api/v1/audit returns filtered audit log with pagination
10. All protected endpoints reject unauthenticated requests (401)
</verification>

<success_criteria>
- External system can POST review item and receive review_id with routing decision (202)
- Reviewer can approve with optional comment (200)
- Reviewer can reject with mandatory reason (200)
- Review status queryable by ID (200/404)
- Reviews listable with status/type/source/priority filters and cursor pagination
- One-time tokens work exactly once for approve/reject
- Audit history queryable per review and with global filters
- JWT auth enforced on all protected endpoints
- All endpoints use consistent {data, meta, error} envelope
</success_criteria>

<output>
After completion, create `.planning/phases/01-core-engine/04-SUMMARY.md`
</output>
