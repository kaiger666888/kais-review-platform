# Phase 10: kais-gold-team Integration - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

GPU tasks in kais-gold-team are automatically intercepted for review before dispatch, and resume on approval or fail on rejection. This phase creates the integration code on both sides: a review client module in the review-platform repo that gold-team imports, and a callback endpoint in gold-team's control_node. It also adds risk-based routing policies for GPU engine types.

Requirements: GT-01, GT-02, GT-03, GT-04, GT-05, GT-06

</domain>

<decisions>
## Implementation Decisions

### Integration Architecture
- Review client code lives in review-platform: `app/integrations/gold_team/client.py` — gold-team imports it as a dependency
- Callback endpoint lives in gold-team repo: `control_node/callback_server.py` — FastAPI endpoint receiving review results
- Review interception at Guardian._dispatch_task() — right before GPU execution, after task picked from inbox

### Risk Scoring & Policy
- YAML policy in review-platform: engine → risk_tier mapping (blender/facefusion = high → HUMAN; tts/woosh/acestep = low → AUTO)
- AUTO-approved reviews return immediately with routing=AUTO, gold-team continues without waiting

### Callback & Recovery
- Guardian waits via polling: checks review status periodically (every 30s) via API
- New "REVIEWING" state in gold-team TaskStatus — task stays in inbox, not dispatched
- Guardian crash recovery: checkpoint with review_id — on restart, query review-platform for status and resume or rollback

### Claude's Discretion
- Exact client API surface (method signatures, error types)
- Polling interval tuning
- Callback endpoint error handling details
- Test strategy (unit vs integration split)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (Review Platform)
- `app/core/state_machine.py` — transition_state() for approve/reject
- `app/core/policy.py` — PolicyEngine with YAML-based rules
- `app/core/events.py` — emit_state_change() triggers callback delivery
- `app/workers/tasks.py` — deliver_review_callback with HMAC signing/retry
- `app/api/v1/reviews.py` — Review submission endpoint (POST /api/v1/reviews)
- `app/models/schemas.py` — ReviewCreateRequest, ReviewResponse schemas

### Reusable Assets (Gold Team - external repo)
- `control_node/scheduler.py` — TaskScheduler.submit_task(), manages queue
- `worker_node/guardian.py` — Guardian scans .inbox/, dispatches to executor, serial GPU execution, checkpoint recovery
- `engines/*.yaml` — Engine definitions: blender, facefusion, acestep, tts, woosh
- `shared/status.py` — TaskStatus enum

### Established Patterns
- Review platform API: POST /api/v1/reviews with source_system, type, metadata, callback_url
- Policy engine: YAML rules with conditions and routing decisions
- Callback delivery: HMAC-SHA256 signed POST to callback_url with retry

### Integration Points
- review-platform API at http://192.168.71.140:8090 — gold-team submits reviews here
- callback_url in review submission → gold-team's callback_server receives result
- Guardian._dispatch_task() → intercept before GPU execution
- Policy engine → new YAML policy for gold-team engine risk scoring

</code_context>

<specifics>
## Specific Ideas

- High-risk engines: blender, facefusion (GPU-intensive, visual output)
- Low-risk engines: tts-forge, woosh, acestep (audio, lightweight)
- Gold-team already uses async/await patterns (asyncio-based Guardian)
- Gold-team uses file-based task passing (.inbox/, .running/, .done/ directories)
- Task metadata available: task_type, params, created_by, priority, tags
- Guardian already has checkpoint recovery mechanism

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>
