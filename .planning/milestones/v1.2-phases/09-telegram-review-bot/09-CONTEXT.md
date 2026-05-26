# Phase 09: Telegram Review Bot - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Reviewers can approve or reject reviews entirely within Telegram, with inline buttons and status feedback. The bot runs in polling mode inside the FastAPI process using python-telegram-bot v22, manages its lifecycle via FastAPI's lifespan, and provides /start, /help, /status commands alongside the core approve/reject InlineKeyboard workflow.

Requirements: TG-01, TG-02, TG-03, TG-04, TG-05, TG-06, TG-07

</domain>

<decisions>
## Implementation Decisions

### Notification Message Layout
- Include review ID, type, source_system, risk_score, priority, submitted time in compact table format
- Message language: Chinese — matches project context and reviewers
- Approval history shown inline: "📋 历史决策: ✓ 张三 2026-05-07 14:30 批准"
- Show content_ref as text snippet (first 100 chars)

### Bot Commands & Interaction
- Support /start (welcome + usage) and /help (commands list) commands
- Support /status command returning count of APPROVING reviews for the chat
- Duplicate callback handling: idempotent — check review state before transition, edit message with "已处理" if already decided

### Error Resilience & Lifecycle
- Bot API unavailable: log error + continue — notifications missed during outage, no retry queue
- Stale InlineKeyboard callback: edit message to "审核已结束: {current_state}" and return
- Bot startup failure: log warning, continue without Bot — API remains functional, Bot disabled gracefully

### Claude's Discretion
- Internal code structure, module organization, exact message template formatting
- Test strategy (unit vs integration split)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/main.py` — FastAPI lifespan with asynccontextmanager pattern, startup/shutdown hooks for Redis and arq pool. Bot init/start/stop should be added here.
- `app/core/state_machine.py` — transition_state() with optimistic locking, audit logging, and emit_state_change. Bot callbacks will call this directly.
- `app/core/config.py` — Settings model already has telegram_bot_token, telegram_allowed_chat_ids, review_timeout (added in Phase 08)
- `app/core/events.py` — emit_state_change() broadcasts SSE + enqueues webhooks. Bot notifications triggered from APPROVING state transitions.
- `app/workers/tasks.py` — arq task pattern with WorkerSettings, check_timeouts cron job. Timeout reminder (TG-06) can leverage this.
- `app/models/schemas.py` — ReviewState enum (PENDING, POLICY_EVAL, APPROVING, COMPLETE)

### Established Patterns
- FastAPI lifespan: asynccontextmanager with yield, startup before yield, shutdown after
- State transitions: transition_state(session, review_id, from_state, to_state, version, actor, action, payload)
- Config: pydantic-settings BaseSettings with .env file support
- Logging: structlog with JSON output
- Async sessions: async_session_factory from app.core.database

### Integration Points
- FastAPI lifespan: add Bot init/start in startup section, Bot stop in shutdown section
- transition_state() called from Bot callback handler for approve/reject
- emit_state_change() triggers when review enters APPROVING → Bot should listen (or be triggered)
- Settings.telegram_bot_token, telegram_allowed_chat_ids, review_timeout already in config
- STATE.md callback_data format: approve:9999:5 (14 bytes, well under 64-byte limit)

</code_context>

<specifics>
## Specific Ideas

- callback_data format already decided: "approve:{review_id}:{version}" and "reject:{review_id}:{version}" (14 bytes max)
- Bot runs inside FastAPI process sharing event loop (no separate process)
- Polling mode only (no webhook — LAN deployment has no public IP)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>
