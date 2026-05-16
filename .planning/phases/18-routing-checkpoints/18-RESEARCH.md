# Phase 18 Research: Routing & Checkpoints

**Researched:** 2026-05-16
**Discovery Level:** Level 0 (all patterns established in codebase)

## Existing Assets

### Policy Engine Output (Phase 17)
- `ShotCardPolicyEngine.evaluate_with_stack()` returns `PolicyResult` with `disposition` (AUTO/HUMAN/AI_AUDIT/BLOCK)
- Aggregator writes `routing_decision` (string: "AUTO"/"HUMAN"/"AI_AUDIT"/"BLOCK") and `policy_commit_sha` to ShotCard via `_write_provenance()`
- `ShotCard.routing_decision` is a PostgreSQL ENUM column (`RoutingDecision` enum)
- Aggregator already fires events via `event_manager.broadcast()` after progressive fill

### Event System (Phase 16)
- `EventManager` in `app/core/events.py`: singleton with asyncio.Queue per SSE connection, broadcast to all, slow-client eviction
- `event_types.py`: Pydantic models for `NodeCompletedEvent`, `BundleReadyEvent`, `ShotCardUpdatedEvent`
- Aggregator emits `shot_card_updated` (every fill) and `bundle_ready` (on bundle completion)
- SSE endpoint in `app/api/routes/sse.py` feeds queue to `StreamingResponse`

### Redis Patterns (V1 established)
- `app/main.py` startup: `aioredis.from_url(settings.redis_url, decode_responses=True)`
- `app/core/auth.py`: one-time tokens with Lua atomic GET+DEL (`consume_review_token`)
- `app.state.redis` accessible via `get_redis(request)` dependency
- Settings already has `redis_url` configured

### State Machine (V1 pattern)
- `app/core/state_machine.py`: 4-state (PENDING->POLICY_EVAL->APPROVING->COMPLETE) with optimistic locking
- `transition_state()` with version checking, audit logging, and event emission
- `VALID_TRANSITIONS` map pattern for state validation

### Timeout Management (V1 pattern)
- `app/workers/tasks.py`: `check_timeouts` cron (every hour), `TIMEOUT_THRESHOLDS` dict
- `WorkerSettings` class with `cron_jobs` list using `arq.cron()`
- `process_node_completion` arq task already registered for aggregation pipeline

### Config (Phase 15)
- `Settings.review_timeout_minutes = 1440` (24h)
- `Settings.ai_audit_timeout_minutes = 5`
- Ready for immediate consumption by timeout manager

## Architecture Decisions

### 1. Approval Router
- Three outlets: `desktop`, `mobile`, `ai_audit`
- Routing decision comes from `ShotCard.routing_decision` (already set by Phase 17 aggregator)
- HUMAN -> desktop OR mobile (for now, both go to desktop; mobile routing deferred to Phase 21)
- AI_AUDIT -> AI outlet (scoring plugin bus stub in Phase 19)
- AUTO -> immediate approval, no queue, ResumeCommand injected
- BLOCK -> immediate rejection
- Priority: derived from node_type in visual_bundle (GPU renders = high, previews = low)
- Redis sorted sets for priority queues (score = priority weight + timestamp)
- Batch approval: group by project_id + narrative_context.scene

### 2. Checkpoint Manager
- RunState Snapshot: serialize ShotCard context (shot_id, execution_id, node completion state) to Redis hash
- Key pattern: `checkpoint:{shot_id}` with TTL matching review timeout
- ResumeCommand: Pydantic model with shot_id, execution_id, approved_at, approved_by
- On approval: create ResumeCommand, emit event, store in Redis for OpenClaw mock consumption
- On rejection: clear checkpoint, emit rejection event

### 3. Timeout Manager
- Extend existing `check_timeouts` pattern from V1
- New arq cron: `check_shot_card_timeouts`
- Query ShotCards with `audit_status = 'awaiting_audit'` and routing_decision set, where updated_at exceeds threshold
- HUMAN route: 24h timeout -> auto-reject
- AI_AUDIT route: 5min timeout -> re-route to HUMAN
- Use Settings values already in config.py

### 4. Event Bus Enhancement
- Add per-outlet filtering to EventManager: connections register with outlet name
- `broadcast_to_outlet(outlet, event_data)`: only deliver to connections subscribed to that outlet
- New event types: `ShotCardRoutedEvent`, `ShotCardApprovedEvent`, `ShotCardRejectedEvent`, `ShotCardTimedOutEvent`
- Keep backward compatibility: `broadcast()` still sends to all unregistered connections

## Key Interfaces to Create

```python
# app/services/approval_router.py
class ApprovalRouter:
    async def route(shot_card: ShotCard) -> RoutingResult
    async def enqueue(shot_card: ShotCard, outlet: str, priority: str) -> None
    async def dequeue(outlet: str, limit: int) -> list[ShotCard]
    async def batch_approve(shot_ids: list[str], actor: str) -> BatchResult

# app/services/checkpoint_manager.py
class CheckpointManager:
    async def save_snapshot(shot_card: ShotCard) -> None
    async def load_snapshot(shot_id: str) -> RunStateSnapshot | None
    async def create_resume_command(shot_id: str, actor: str) -> ResumeCommand
    async def clear_checkpoint(shot_id: str) -> None

# app/services/timeout_manager.py (or extend workers/tasks.py)
async def check_shot_card_timeouts(ctx: dict) -> list[str]

# Enhanced EventManager
class EventManager:
    def create_connection(outlet: str | None = None) -> asyncio.Queue
    async def broadcast_to_outlet(outlet: str, event_data: dict) -> None
```

## Redis Key Design

| Key Pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `queue:desktop:high` | Sorted Set | None | High-priority desktop queue |
| `queue:desktop:low` | Sorted Set | None | Low-priority desktop queue |
| `queue:ai_audit` | Sorted Set | None | AI audit queue |
| `checkpoint:{shot_id}` | Hash | 24h | RunState snapshot |
| `resume:{execution_id}` | String (JSON) | 1h | ResumeCommand for OpenClaw pickup |
| `timeout:shot:{shot_id}` | String | Per route type | Timeout tracking |

## Dependency Analysis

```
Plan 01 (Approval Router):
  needs: ShotCard model (Phase 15), routing_decision (Phase 17), Redis
  creates: ApprovalRouter, RoutingResult, priority queues in Redis

Plan 02 (Checkpoint + Timeout):
  needs: ShotCard model (Phase 15), Redis, config timeouts (Phase 15)
  creates: CheckpointManager, RunStateSnapshot, ResumeCommand, shot card timeout cron
  depends on: Plan 01 (router sets the timeout key when routing)

Plan 03 (Event Bus):
  needs: EventManager (existing), event types (Phase 16)
  creates: Enhanced EventManager with outlet filtering, new event types
  depends on: Plan 01 (routed event), Plan 02 (approved/rejected events)
```

## Risk Assessment

- **Priority derivation from node_type:** Need to inspect visual_bundle structure to determine GPU render vs preview. May need a heuristic (e.g., presence of video_clip = high priority, only keyframes = low)
- **Batch approval atomicity:** Multiple ShotCards approved in one operation must all succeed or all fail. Use Redis pipeline + database transaction.
- **Timeout cron frequency:** 5-minute AI timeout means cron must run at least every 60 seconds for timely escalation. Use `second={0}` or `minute=[*]` for AI, hourly for human.
