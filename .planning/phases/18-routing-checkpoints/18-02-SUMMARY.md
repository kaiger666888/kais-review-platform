---
phase: 18-routing-checkpoints
plan: 02
subsystem: services
tags: [redis, checkpoint, timeout, arq-cron, pydantic, audit-trail]

requires:
  - phase: 18-routing-checkpoints/01
    provides: ApprovalRouter service, priority queue

provides:
  - RunStateSnapshot and ResumeCommand Pydantic models for pipeline state serialization
  - CheckpointManager service with save/load/resume/clear operations
  - Shot card timeout cron (24h HUMAN auto-reject, 5min AI_AUDIT escalate)
  - ShotCardTimeoutSettings dataclass for testable timeout configuration
  - create_audit_entry helper for timeout audit trail entries

affects: [arq-worker, shot-card-lifecycle, pipeline-resume, audit-trail]

tech-stack:
  added: []
  patterns: [redis-hash-checkpoint, route-type-ttl, timeout-config-dataclass, cron-timeout-escalation]

key-files:
  created:
    - app/core/checkpoint_types.py
    - app/services/checkpoint_manager.py
    - app/workers/shot_card_timeouts.py
    - tests/test_checkpoint_manager.py
    - tests/test_shot_card_timeouts.py
  modified:
    - app/models/schemas.py
    - app/models/__init__.py
    - tests/conftest.py

key-decisions:
  - "Checkpoint stored as Redis hash at checkpoint:{shot_id}, ResumeCommand as JSON string at resume:{execution_id} with 1h TTL"
  - "TTL per route type: 24h (HUMAN), 5min (AI_AUDIT), 0 (AUTO/BLOCK immediate cleanup)"
  - "Timeout function uses direct DB updates instead of ApprovalRouter class (router does not have reject/enqueue methods yet)"
  - "Module-level imports in shot_card_timeouts.py for testability (patchable by test mocks)"
  - "Timeout audit entries use simplified hash chain (prev_hash='timeout') separate from main state machine chain"

patterns-established:
  - "Route-type TTL: checkpoint TTL matches review timeout per routing decision"
  - "Convenience lifecycle methods: on_approval (load->resume->clear), on_rejection (clear+event)"
  - "Timeout config dataclass: ShotCardTimeoutSettings wraps TIMEOUT_CONFIG for injection"

requirements-completed: [CHKP-01, CHKP-02]

duration: 13min
completed: 2026-05-16
---

# Phase 18 Plan 02: Checkpoint Manager + Timeout Escalation Summary

**RunState snapshots serialized to Redis hashes with route-type TTL, ResumeCommands on approval, and graded timeout policy (24h auto-reject / 5min escalate) as arq cron**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-16T12:15:48Z
- **Completed:** 2026-05-16T12:28:53Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- CheckpointManager with full lifecycle: save snapshot, load, create resume command, clear
- RunStateSnapshot captures all ShotCard execution context (narrative, visual, audio bundles)
- ResumeCommand with UUID command_id and 1h TTL in Redis for pipeline resume
- Timeout cron: HUMAN >24h auto-reject with audit trail, AI_AUDIT >5min escalate to HUMAN
- 22 new tests covering checkpoint lifecycle and timeout escalation

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): CheckpointManager failing tests** - `2c8a3e9` (test)
2. **Task 1 (GREEN): CheckpointManager implementation** - `e3e6e26` (feat)
3. **Task 2 (RED): Timeout manager failing tests** - `08af53c` (test)
4. **Task 2 (GREEN): Timeout manager implementation** - `dc15006` (feat)

## Files Created/Modified
- `app/core/checkpoint_types.py` - RunStateSnapshot, ResumeCommand, ShotCardApprovedEvent, ShotCardRejectedEvent models
- `app/services/checkpoint_manager.py` - CheckpointManager with save/load/resume/clear/on_approval/on_rejection
- `app/workers/shot_card_timeouts.py` - check_shot_card_timeouts cron, ShotCardTimeoutSettings, create_audit_entry helper
- `tests/test_checkpoint_manager.py` - 14 tests for checkpoint lifecycle
- `tests/test_shot_card_timeouts.py` - 8 tests for timeout escalation
- `app/models/schemas.py` - Added ReviewState enum (missing V1 compat)
- `app/models/__init__.py` - Fixed stale imports, added ReviewState
- `tests/conftest.py` - Added POSTGRES_URL env var for V2 compatibility

## Decisions Made
- Checkpoint as Redis hash (HSET/HGETALL) allows partial field reads and individual field updates
- ResumeCommand stored separately at resume:{execution_id} (not embedded in checkpoint) for independent TTL management
- Timeout function operates directly on ShotCard ORM objects rather than calling a router service, keeping the cron self-contained
- Audit entries for timeouts use prev_hash="timeout" to start their own chain, avoiding hash chain corruption from the main state machine

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed stale imports in app/models/__init__.py**
- **Found during:** Task 1 (test collection)
- **Issue:** __init__.py imported ApproveRequest, RejectRequest, ReviewState and other symbols that do not exist in schemas.py, causing ImportError for all tests
- **Fix:** Removed 11 non-existent imports, kept only symbols that exist in schemas.py
- **Files modified:** app/models/__init__.py
- **Verification:** Tests collect and pass
- **Committed in:** 2c8a3e9 (Task 1 RED commit)

**2. [Rule 3 - Blocking] Added POSTGRES_URL to test conftest and .env**
- **Found during:** Task 1 (test collection)
- **Issue:** .env had stale DATABASE_URL (V1 SQLite) but Settings expects postgres_url; pydantic-settings rejected the extra field
- **Fix:** Added POSTGRES_URL env var to conftest.py, updated .env to use POSTGRES_URL
- **Files modified:** tests/conftest.py, .env
- **Verification:** Settings() instantiates without ValidationError
- **Committed in:** e3e6e26 (Task 1 GREEN commit)

**3. [Rule 3 - Blocking] Added ReviewState enum to schemas.py**
- **Found during:** Task 2 (module import)
- **Issue:** approval_router.py imports ReviewState from schemas.py but it was never defined, causing ImportError through the entire import chain
- **Fix:** Added ReviewState(str, enum.Enum) with PENDING, POLICY_EVAL, APPROVING, COMPLETE values
- **Files modified:** app/models/schemas.py, app/models/__init__.py
- **Verification:** All imports succeed, tests pass
- **Committed in:** dc15006 (Task 2 GREEN commit)

**4. [Rule 1 - Bug] Removed ApprovalRouter dependency from timeout cron**
- **Found during:** Task 2 (implementation)
- **Issue:** Plan referenced ApprovalRouter class with reject_single/enqueue methods, but approval_router.py only has function exports (build_approval_queue_query, get_priority_sorted_reviews). The class does not exist.
- **Fix:** Timeout function operates directly on ShotCard ORM objects: sets audit_status to REJECTED for auto-reject, updates routing_decision to HUMAN for escalation
- **Files modified:** app/workers/shot_card_timeouts.py, tests/test_shot_card_timeouts.py
- **Verification:** 8 timeout tests pass
- **Committed in:** dc15006 (Task 2 GREEN commit)

---

**Total deviations:** 4 auto-fixed (3 blocking, 1 bug)
**Impact on plan:** All auto-fixes necessary for test execution and correct implementation. No scope creep.

## Issues Encountered
- V1-to-V2 migration left several broken import chains (ReviewState, stale __init__.py, .env mismatch). Fixed inline to unblock execution.

## Wiring Note

The timeout cron `check_shot_card_timeouts` should be wired into arq WorkerSettings in `app/workers/tasks.py`:

```python
from app.workers.shot_card_timeouts import check_shot_card_timeouts

class WorkerSettings:
    functions = [...existing..., check_shot_card_timeouts]
    cron_jobs = [
        ...existing...,
        cron(check_shot_card_timeouts, second=0),  # Every minute for AI audit responsiveness
    ]
```

This wiring is documented here for manual integration rather than modifying tasks.py to avoid circular import risk.

## Next Phase Readiness
- CheckpointManager ready for integration with approval flow (router calls on_approval/on_rejection)
- Timeout cron ready for wiring into arq WorkerSettings
- RunStateSnapshot format stable for pipeline resume implementation
- ResumeCommand format ready for OpenClaw execution layer consumption

---
*Phase: 18-routing-checkpoints*
*Completed: 2026-05-16*

## Self-Check: PASSED

- All 6 created files found on disk
- All 4 commits found in git log
- 22 tests passing (14 checkpoint + 8 timeout)
