# Phase 18: Routing & Checkpoints - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase)

<domain>
## Phase Boundary

Shot Cards are dynamically routed to the correct review outlet with priority ordering, and pipeline execution state is preserved for resume after approval. This phase builds the Approval Router, Checkpoint Manager, and enhanced Event Bus.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices at Claude's discretion. Key references:
- `.planning/research/V2-ARCHITECTURE.md` — Approval Router, Checkpoint Manager, Event Bus design
- `app/core/policy_v2.py` — ShotCardPolicyEngine (provides routing decisions)
- `app/services/aggregator.py` — Aggregator (triggers routing after policy evaluation)
- `app/core/state_machine.py` — V1 state machine (pattern reference)
- `app/core/events.py` — V1 EventManager (extend for per-outlet routing)
- `app/core/event_types.py` — Event types from Phase 16

### Pre-established Decisions
- Three outlets: Desktop queue, Mobile queue, AI Audit interface
- Priority queues: high (GPU renders), low (preview cards)
- Batch approval for same-scene Shot Cards
- Redis for RunState Snapshots and timeout tracking
- 24h timeout for human review → auto-reject
- 5min timeout for AI review → escalate to human
- Per-outlet event filtering (desktop vs mobile)
- OpenClaw integration via mocks

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/core/policy_v2.py` — Returns routing decisions (AUTO/HUMAN/AI_AUDIT/BLOCK)
- `app/services/aggregator.py` — Integration point after policy evaluation
- `app/core/events.py` — EventManager with broadcast pattern
- `app/core/event_types.py` — Existing event types
- `app/core/state_machine.py` — V1 state machine with optimistic locking
- `app/models/shot_card.py` — ShotCard model with audit_state JSONB

### Integration Points
- Router receives routing_decision from policy engine output
- Checkpoint manager serializes to Redis after routing
- Event bus broadcasts routing events per-outlet
- Timeout manager runs as arq cron

</code_context>

<specifics>
## Specific Ideas

Follow V2 architecture spec for approval router and checkpoint manager patterns.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.
