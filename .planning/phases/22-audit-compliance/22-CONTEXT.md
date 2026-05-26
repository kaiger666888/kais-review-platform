# Phase 22: Audit & Compliance - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous workflow)

<domain>
## Phase Boundary

Every decision is tamper-evident via Merkle Root anchoring, tiered storage manages data lifecycle automatically, multi-role auth controls access across the platform, and desktop/mobile audit dashboards provide review analytics.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices at Claude's discretion — autonomous mode. Use ROADMAP phase goal, success criteria, codebase conventions, and Notion V2 architecture spec.

Key architecture requirements:
- Merkle Root: daily computation of audit log hash tree, committed to Git, verification endpoint
- Dual-write audit recorder: real-time PostgreSQL + async archive to MinIO JSONL
- Tiered storage lifecycle: 30d hot (PostgreSQL) → 1yr warm (MinIO JSONL) → permanent cold (WORM)
- arq cron workers for automated archival
- Multi-role auth: admin (policy mgmt), reviewer (desktop/mobile), auditor (read-only), ai_service (scoring)
- Desktop audit cockpit: timeline, statistics (throughput, rejection reasons, policy hit rates), policy version diff
- Mobile audit dashboard: stats, review waterfall, detail pages

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- app/core/audit.py — AuditLogger with SHA-256 hash chain (foundation for Merkle Root)
- app/core/auth.py — JWT auth, one-time review tokens, Redis token management
- app/models/shot_card.py — AuditEntry SQLAlchemy model with composite PK
- app/api/v1/audit_api.py — Existing audit query endpoints
- app/services/scoring_bus.py — Shadow mode recording (feedback data to cold storage)
- app/workers/tasks.py — arq cron task patterns (check_timeouts, send_reminders)

### Established Patterns
- arq cron workers for background tasks
- FastAPI router with async handlers
- PostgreSQL async via asyncpg/SQLAlchemy
- MinIO client for object storage
- Git integration via GitPolicyProvider

### Integration Points
- app/core/audit.py — extend append_audit() for dual-write
- app/workers/tasks.py — add lifecycle management cron jobs
- app/core/auth.py — extend with role-based access control
- app/main.py — register new routers and cron tasks

</code_context>

<specifics>
## Specific Ideas

Follow Notion V2 architecture sections 六 (audit data layer) and 九 (key decisions 5-7):
- Merkle Root anchoring for tamper-evident audit log
- Dual-write for real-time + archive audit storage
- Tiered storage with configurable retention policies

</specifics>

<deferred>
## Deferred Ideas

None — autonomous mode.
</deferred>
