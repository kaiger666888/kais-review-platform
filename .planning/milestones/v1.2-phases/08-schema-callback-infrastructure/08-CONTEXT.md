# Phase 08: Schema & Callback Infrastructure - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — no interactive discuss needed)

<domain>
## Phase Boundary

External systems can register a callback URL when submitting reviews, and the platform reliably delivers signed results when reviews complete. This phase adds per-review callback fields to the database model, creates a new arq task for callback delivery with HMAC signing and retry logic, validates callback URLs against RFC1918 addresses, and sends Telegram admin notifications on exhausted retries.

Requirements: DB-01, DB-02, DB-03, DB-04, CB-01, CB-02, CB-03, CB-04, CB-05

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models/schema.py` — SQLAlchemy models: Review (no callback fields yet), WebhookConfig (has url/secret pattern), AuditEntry, PolicyVersion
- `app/workers/tasks.py` — arq tasks: deliver_webhook (HMAC signing, retry with backoff), check_timeouts (cron). Uses Retry exception, httpx.AsyncClient
- `app/core/events.py` — emit_state_change() broadcasts SSE + enqueues webhook deliveries via arq pool
- `app/core/config.py` — pydantic-settings BaseSettings with env vars. No Telegram config yet
- `app/models/schemas.py` — Pydantic request/response models. ReviewCreateRequest, ReviewResponse

### Established Patterns
- HMAC signing pattern: `hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()` in deliver_webhook
- Retry pattern: arq Retry exception with WEBHOOK_BACKOFF dict {1: 1, 2: 5, 3: 30}
- arq task signature: `async def task(ctx: dict, ...) -> dict`
- Worker settings class: WorkerSettings with functions, cron_jobs, on_startup/on_shutdown
- Database: SQLAlchemy async sessions via async_session_factory

### Integration Points
- Review model needs callback_url + callback_secret columns (DB-01, DB-02)
- Settings model needs telegram_bot_token, telegram_allowed_chat_ids, review_timeout (DB-03)
- ReviewCreateRequest needs callback_url + callback_secret fields
- emit_state_change() should trigger callback delivery when review reaches COMPLETE state
- deliver_review_callback arq task follows same pattern as deliver_webhook
- RFC1918 validation needed at review submission time (CB-04)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase, scope is clear from requirements.
</deferred>
