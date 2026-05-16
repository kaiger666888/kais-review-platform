# Phase 19: AI Audit & Capability Tokens - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

AI audit interfaces exist as verified stubs returning empty vectors with shadow-mode recording, and capability tokens gate downstream GPU execution after approval. This phase creates the scoring plugin bus, shadow mode recorder, model registry placeholder, feedback loop stub, A/B test interface, and capability token issuance/verification — all as Phase 0 stubs ready for real AI model integration later.

</domain>

<decisions>
## Implementation Decisions

### Scoring Plugin Bus & Model Registry
- Plugin protocol class — abstract `ScoringPlugin` with `name`, `version`, `score(shot_card) -> ScoreVector`, registered via list in Settings
- Single `NullScoringPlugin` returns empty vectors in Phase 0, extensible later
- 5 score dimensions: aesthetics, consistency, compliance, technical_quality, audio_match — each returns `null` in Phase 0
- In-memory `ModelRegistry` dict — `get_model(name) -> ModelInfo` returns `model_unavailable` for all queries, no database needed
- Shadow mode triggers after every human review decision via arq background task, writes to `shadow_scores` table alongside human decision

### Capability Token Design
- JWT format — reuses existing PyJWT dependency, `capability_token_secret` already in Settings
- Payload: `shot_id`, `node_scope` (flat list of authorized node IDs), `issued_at`, `expires_at`
- Single-use tokens — issued on approval, verified once by downstream, then invalidated. Redis TTL 1hr auto-expiry
- Verification endpoint: `POST /api/v1/tokens/verify` — accepts token string, returns `{valid, shot_id, node_scope, expires_at}` or `{valid: false, reason}`. Checks Redis for revocation

### A/B Test & Feedback Data
- PostgreSQL table `ab_test_pairs` — columns: `batch_id`, `shot_id`, `ai_score` (JSONB), `human_decision`, `created_at`, queryable by `batch_id`
- Feedback loop writes to MinIO cold storage JSONL: `{bucket}/feedback/{date}/{project_id}.jsonl` — no PostgreSQL write for feedback (Phase 22 handles tiered storage)
- A/B batch creation via API endpoint only — `POST /api/v1/ab-tests` accepts list of shot_ids, creates batch, returns `batch_id`

### Claude's Discretion
Implementation details for scoring bus internals, error handling patterns, and test structure are at Claude's discretion.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models/shot_card.py` — ShotCard model with `RoutingDecision` enum (includes `AI_AUDIT`)
- `app/services/approval_router.py` — Routes Shot Cards to outlets based on policy decision
- `app/services/checkpoint_manager.py` — TTL management with `"AI_AUDIT": 300` (5 minutes)
- `app/core/config.py` — Settings with `capability_token_secret` and `ai_audit_timeout_minutes`
- `app/core/events.py` — EventManager with broadcast pattern
- `app/core/policy.py` — PolicyEngine returning routing decisions
- `app/workers/shot_card_timeouts.py` — Timeout escalation worker

### Established Patterns
- SQLAlchemy models in `app/models/`, Pydantic schemas in `app/models/schemas.py`
- Services in `app/services/`, API routes in `app/api/v1/`
- arq workers in `app/workers/`, registered in `app/workers/__init__.py`
- Redis for stateful data (checkpoints, timeouts), PostgreSQL for persistent data
- Event bus broadcasts via SSE

### Integration Points
- Scoring bus called by approval router when routing_decision is AI_AUDIT
- Shadow mode hooks into post-review flow (after human decision)
- Capability token issued after approval (in approval flow)
- A/B test API is standalone endpoint
- Feedback loop writes to MinIO (config in Settings)

</code_context>

<specifics>
## Specific Ideas

Follow V2 architecture spec patterns. All implementations are Phase 0 stubs — verified to return correct empty/placeholder data, not production AI scoring. Focus on clean interfaces for future Phase 1-4 AI integration.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
