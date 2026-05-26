# V1 -> V2 Gap Analysis

> Generated: 2026-05-16
> Source: V2-ARCHITECTURE.md vs current codebase audit

## Executive Summary

The V2 architecture represents a fundamental paradigm shift from a **generic review queue** (V1) to a **production-pipeline governance platform** centered on the **Shot Card** concept. The current V1 codebase provides a working review lifecycle (submit, evaluate, route, approve/reject) with SQLite storage, YAML policies, SSE push, Telegram notifications, and a basic HTMX dashboard. However, it lacks every V2-specific concept: Shot Card aggregation, GitOps version control, tiered storage, desktop workstation UI, mobile PWA, AI audit window, and Merkle Root anchoring.

**Scale of transformation:** 4 new architectural layers, ~15 new components, data model rewrite, database migration, dual-frontend rebuild. This is a major version upgrade, not an incremental feature release.

---

## Layer 1: GitOps Version Control Plane

### V2 Requirement

All governance decision logic lives in Git. Runtime reads from a specific commit SHA. Versioned objects include:
- Workflow definitions (OpenClaw pipeline JSON/YAML)
- Policy rules (YAML) with PR-based approval for changes
- AI audit assets (model configs, prompt templates, weight file references)
- Shot Card definition templates (bundle rules, min-audit-set config)
- Audit anchoring (daily Merkle Root of audit log written to Git)

### Current V1 State

| Aspect | V1 Current | V2 Required |
|--------|-----------|-------------|
| Policy storage | YAML files on disk (`app/policies/default.yaml`), loaded into memory at startup via `PolicyEngine.load_from_directory()`. Also stored in `policy_versions` SQLite table via API. | Policy-as-code in Git repo. Each policy change is a PR. Runtime references `policy_commit_sha`. Audit log records which policy commit was used. |
| Policy versioning | `PolicyVersion` table stores `name`, `version`, `content`, `is_active`. CRUD via `/api/v1/policies`. No Git integration. | Git commit SHA bound to every evaluation. `provenance.policy_commit_sha` on every Shot Card. Rollback = checkout old commit. |
| Workflow definitions | None. No concept of workflow, pipeline, or DAG. | OpenClaw pipeline definitions versioned in Git with tags. `workflow_version` hash recorded in audit trail. |
| Shot Card templates | None. No Shot Card concept. | Git-managed YAML defining which node outputs aggregate into a Shot Card, min-audit-set rules, bundle structure. |
| AI audit assets | None. `AI_AUDIT` disposition exists in policy engine but is treated identically to `HUMAN` (routed to human). | Model configs, prompt templates, scoring weights stored in Git with hash references. Bound to audit records. |
| Audit anchoring | SHA-256 hash chain per review (`AuditEntry.prev_hash` / `own_hash`). No cross-review Merkle tree. No Git anchoring. | Daily Merkle Root computed across all audit entries, committed to Git. Enables tamper detection across the entire audit log. |
| Runtime config resolution | `get_settings()` reads `.env` via pydantic-settings. Policy engine reads YAML from filesystem. | Runtime reads from a specific Git commit. `workflow_version`, `policy_commit_sha`, `model_version` all pinned. |

### Gaps

#### GAP-1.1: Git Repository Integration
- **What exists:** Filesystem YAML loading (`PolicyEngine.load_from_directory("app/policies")`)
- **What V2 requires:** Full Git repo integration -- clone/fetch a governance repo, resolve refs, read files at specific commits, compute commit SHAs
- **Effort:** MEDIUM
- **Dependencies:** None (foundational)

#### GAP-1.2: Policy-as-Code with PR Approval
- **What exists:** Direct policy CRUD via REST API (`/api/v1/policies`), no approval workflow
- **What V2 requires:** Policy changes go through Git PR workflow. API becomes read-only (reads from Git). PR merge triggers policy reload.
- **Effort:** MEDIUM
- **Dependencies:** GAP-1.1

#### GAP-1.3: Provenance Tracking (commit SHA binding)
- **What exists:** `Review` model has no provenance fields. `AuditEntry` has no policy/workflow version references.
- **What V2 requires:** Every Shot Card carries `provenance.workflow_version`, `provenance.policy_commit_sha`, `provenance.execution_id`. Every audit entry records the policy version used.
- **Effort:** SMALL
- **Dependencies:** GAP-1.1, GAP-2.1 (Shot Card model)

#### GAP-1.4: Audit Merkle Root Anchoring
- **What exists:** Per-review SHA-256 hash chain (`AuditEntry.prev_hash` / `own_hash`). Authorizer blocks UPDATE/DELETE on `audit_entries` table.
- **What V2 requires:** Daily (or periodic) Merkle tree computed across all audit entries. Root hash committed to Git. Verification endpoint to check tampering.
- **Effort:** MEDIUM
- **Dependencies:** GAP-4.2 (audit data layer stability)

#### GAP-1.5: Workflow Definition Versioning
- **What exists:** None. No workflow or pipeline concept.
- **What V2 requires:** OpenClaw pipeline JSON/YAML stored in Git. Tagged versions. `workflow_version` hash on every Shot Card.
- **Effort:** SMALL (store and reference) / LARGE (integrate with OpenClaw)
- **Dependencies:** GAP-1.1, external OpenClaw integration

#### GAP-1.6: Shot Card Template Versioning
- **What exists:** None. No Shot Card concept.
- **What V2 requires:** YAML templates defining bundle rules, min-audit-set config. Versioned in Git. Each Shot Card instance references the template version it was created from.
- **Effort:** SMALL
- **Dependencies:** GAP-1.1, GAP-2.1

---

## Layer 2: Governance Core Engine

### V2 Requirement

Seven core components: Policy Engine (enhanced), Shot Card Aggregator, Checkpoint Manager, Approval Router, Token Service (enhanced), Audit Recorder (enhanced), Event Bus (enhanced), plus the new Topology Collapser.

### Current V1 State

| Component | V1 Implementation | V2 Requirement |
|-----------|------------------|----------------|
| Policy Engine | `PolicyEngine` class in `app/core/policy.py`. YAML rules with AND/OR conditions, JSON Schema validation. Evaluates `review_data` dict against rules. Returns `Disposition` enum (AUTO/HUMAN/AI_AUDIT/BLOCK). | Enhanced: policy stacking (global + project + temporary), Shot Card as input (not flat dict), reads from Git commit, narrative_context awareness (risk tags, cost level) |
| Shot Card Aggregator | None. Reviews are submitted as flat items with `type`, `content_ref`, `metadata`. No aggregation, no progressive fill. | Listens to OpenClaw events, groups node outputs by `shot_id`, progressively fills visual_bundle then audio_bundle, unlocks review when min_audit_set is satisfied |
| Checkpoint Manager | `state_machine.py` with 4 states (PENDING -> POLICY_EVAL -> APPROVING -> COMPLETE). Optimistic locking. Timeout escalation via `check_timeouts` cron. Redis stores one-time tokens only. | Per-Shot Card RunState Snapshots in Redis. OpenClaw DAG execution state serialized. ResumeCommand injection after approval. GPU cost-aware timeout (5min AI, 24h human). |
| Approval Router | Implicit in `submit_review()`: policy evaluation returns disposition, then direct state transition. No queue management, no priority queuing, no batch processing. | Dynamic routing to 3 outlets (Human Desktop, Human Mobile, AI Audit). Priority queues (high for 3090 renders, low for preview cards). Batch approval for same-scene Shot Cards. |
| Token Service | `app/core/auth.py`: JWT (15min, HS256) for API auth. One-time review tokens in Redis (72h TTL) for deep-linking. `consume_review_token()` with Lua atomic GET+DEL. | Enhanced: Capability Tokens -- post-approval tokens issued to OpenClaw to authorize downstream execution. Without token, high-cost GPU tasks are refused by execution layer. |
| Audit Recorder | `app/core/audit.py`: `AuditLogger` with SHA-256 hash chain. `append_audit()` convenience function. SQLite authorizer blocks UPDATE/DELETE. | Structured schema with Shot Card context. Dual-write: real-time to timeseries DB + async archive to immutable storage. Richer schema (node states, candidate scores, policy commit refs). |
| Event Bus | `app/core/events.py`: `EventManager` with asyncio.Queue per SSE connection. `emit_state_change()` broadcasts to SSE + enqueues webhook delivery + Telegram notification. | Enhanced: progressive fill events (node completion updates Shot Card partial state), OpenClaw event bus integration, WebSocket option alongside SSE, webhook fan-out per outlet. |
| Topology Collapser | None. No DAG or topology concept. | Listens to OpenClaw DAG events. Extracts `shot_id` from node metadata. Maps flat node outputs to Shot Card bundles. Implements the "fold" from execution topology to narrative unit. |

### Gaps

#### GAP-2.1: Shot Card Data Model
- **What exists:** `Review` model: `id`, `type`, `content_ref`, `metadata_json`, `source_system`, `priority`, `risk_score`, `state`, `disposition`, `callback_url`, `callback_secret`, `version`, timestamps. Flat structure.
- **What V2 requires:** Rich nested model: `shot_id`, `project_id`, `narrative_context` (scene, shot_number, emotion_curve, continuity_tags), `visual_bundle` (keyframes, video_clip, prompt, candidates), `audio_bundle` (bgm_prompt, sfx_prompt, status), `audit_state` (status, routing_decision, min_audit_set, blocking_reason), `provenance` (workflow_version, policy_commit_sha, execution_id).
- **Effort:** LARGE -- this is the foundational data model change that everything else depends on
- **Dependencies:** None (foundational, but everything else depends on this)

#### GAP-2.2: Shot Card Aggregator
- **What exists:** None. Reviews are submitted as atomic units via POST `/api/v1/reviews`.
- **What V2 requires:** New service that listens to OpenClaw events, groups outputs by `shot_id`, progressively fills Shot Card fields. Manages min_audit_set logic. Fires "bundle ready" events when review can proceed.
- **Effort:** LARGE
- **Dependencies:** GAP-2.1, GAP-2.8 (Topology Collapser), external OpenClaw event integration

#### GAP-2.3: Enhanced Policy Engine (Shot Card aware, policy stacking)
- **What exists:** Flat dict evaluation with AND/OR conditions. Single policy evaluation. No stacking.
- **What V2 requires:** (1) Input is Shot Card, not flat dict. (2) Policy stacking: global + project + temporary policies evaluated in layers. (3) Narrative context awareness: risk tags, cost level from emotion_curve/continuity_tags. (4) Reads policy from Git commit, not filesystem.
- **Effort:** MEDIUM
- **Dependencies:** GAP-1.1, GAP-2.1

#### GAP-2.4: Checkpoint Manager (RunState Snapshots)
- **What exists:** 4-state machine in SQLite with optimistic locking. `check_timeouts` cron escalates APPROVING -> POLICY_EVAL after 24h. No DAG state serialization.
- **What V2 requires:** Per-Shot Card snapshots of OpenClaw DAG execution state in Redis. ResumeCommand injection post-approval. Granular timeouts per route type. Integration with OpenClaw execution layer.
- **Effort:** LARGE
- **Dependencies:** GAP-2.1, GAP-2.2, external OpenClaw integration

#### GAP-2.5: Approval Router (Priority Queues, Batch Processing)
- **What exists:** Implicit routing in `submit_review()`: disposition -> state transition. No queue management, no batch operations.
- **What V2 requires:** Explicit routing component with priority queues. High-priority queue for GPU renders, low-priority for preview cards. Batch approval API for same-scene Shot Cards. Three distinct outlets: Desktop, Mobile, AI.
- **Effort:** MEDIUM
- **Dependencies:** GAP-2.1, GAP-2.2

#### GAP-2.6: Capability Token Service
- **What exists:** One-time review tokens (Redis-backed, 72h TTL, Lua atomic consume). JWT for API auth. No post-approval execution authorization.
- **What V2 requires:** Capability Tokens issued after approval. Sent to OpenClaw execution layer. GPU tasks without valid Capability Token are refused. Tokens encode authorization scope (which nodes can execute, resource limits).
- **Effort:** MEDIUM
- **Dependencies:** GAP-2.4, external OpenClaw integration

#### GAP-2.7: Enhanced Audit Recorder (Dual-Write)
- **What exists:** Single-write to SQLite `audit_entries` table. SHA-256 hash chain per review. SQLite authorizer for immutability.
- **What V2 requires:** Dual-write: real-time to timeseries DB (PostgreSQL/TimescaleDB) + async archive to immutable object storage. Richer schema with Shot Card context, node states, candidate scores, policy commit refs.
- **Effort:** LARGE (ties into GAP-4.1 database migration)
- **Dependencies:** GAP-4.1, GAP-2.1

#### GAP-2.8: Event Bus Enhancements
- **What exists:** `EventManager` with asyncio.Queue per SSE connection (maxsize=100). Broadcast to all connections. `emit_state_change()` -> SSE + webhook + Telegram. Max 50 connection warning.
- **What V2 requires:** Progressive fill events (node completion -> partial Shot Card update). OpenClaw event bus integration. Per-outlet routing (desktop gets different events than mobile). WebSocket support alongside SSE. Event types: `node_completed`, `bundle_ready`, `review_decided`, `shot_card_updated`.
- **Effort:** MEDIUM
- **Dependencies:** GAP-2.1, GAP-2.2

#### GAP-2.9: Topology Collapser
- **What exists:** None. No concept of execution topology, DAG, or node-to-shot mapping.
- **What V2 requires:** New component that maps OpenClaw DAG node outputs to Shot Cards. Extracts `shot_id` from node metadata. Implements the "fold" from flat execution events to narrative Shot Card bundles. Must handle out-of-order completion (video before image, audio before visual).
- **Effort:** LARGE
- **Dependencies:** GAP-2.1, GAP-2.2, external OpenClaw integration

---

## Layer 3: Review Outlets

### V2 Requirement

Three review outlets: Desktop 3-column workstation, Mobile PWA card flow, AI Audit window (scoring plugin bus + model registry + feedback loop).

### Current V1 State

| Outlet | V1 Implementation | V2 Requirement |
|--------|------------------|----------------|
| Desktop Web | Single-column HTMX dashboard. Tab-based (pending/approved/rejected). Card list + detail overlay. SSE for real-time updates. Jinja2 templates with Tailwind CSS. | 3-column workstation: left queue panel, center Shot Card preview (video player, keyframe viewer, candidate array), right metadata/decision panel. Keyboard shortcuts (Space, Y/N, J/K, D for diff, B for batch). Dual-column comparison. Candidate array with thumbnail grid. |
| Mobile | Telegram Bot (`python-telegram-bot`). Inline keyboard approve/reject. Preview image delivery. `/status` command. No web-based mobile experience. | PWA with card-flow layout. Vertical swipe for shot navigation, horizontal swipe for candidate switching. Gesture controls (swipe left=approve, right=reject). Service Worker for offline cache (20 Shot Cards). Context bar showing scene/shot/emotion. |
| AI Audit | `AI_AUDIT` disposition exists in policy engine but routes identically to `HUMAN` (goes to APPROVING state, waits for human). | Full AI audit extension: scoring plugin bus, model registry, feedback loop, A/B test interface, shadow mode, circuit breaker. Phase 0 = empty vector, fallback to human. |

### Gaps

#### GAP-3.1: Desktop 3-Column Workstation UI
- **What exists:** HTMX dashboard (`app/templates/pages/dashboard.html`). Single column review list with tab navigation (pending/approved/rejected). Detail overlay. SSE-driven refresh via `hx-ext="sse"`. No video player, no comparison view, no keyboard shortcuts, no candidate array.
- **What V2 requires:** Complete UI redesign to 3-column layout. Left panel: filtered queue with project/scene/risk filters, keyboard navigation. Center panel: Shot Card preview with video player, keyframe viewer, timeline scrubber, candidate thumbnail grid. Right panel: narrative context, prompt summary, node status, decision buttons. Keyboard shortcuts for power users. Batch selection. Git policy diff viewer.
- **Effort:** LARGE
- **Dependencies:** GAP-2.1 (Shot Card data model), GAP-2.2 (aggregator for progressive fill data)

#### GAP-3.2: Mobile PWA
- **What exists:** Telegram Bot with InlineKeyboard approve/reject buttons. `python-telegram-bot` handlers. Preview images sent as bot messages. No web-based mobile interface at all.
- **What V2 requires:** Full PWA with Service Worker, manifest.json, offline caching. Card-flow layout with gesture controls. Vertical/horizontal swipe navigation. Collapsible prompt/audio sections. Two-finger pinch zoom. Offline queue for 20 most recent Shot Cards.
- **Effort:** LARGE
- **Dependencies:** GAP-2.1, GAP-3.3 (may need separate backend API for PWA), PWA infrastructure (manifest, service worker, HTTPS)

#### GAP-3.3: Mobile API Backend
- **What exists:** API returns flat `ReviewResponse` objects. No Shot Card structure, no candidate data, no progressive fill endpoints.
- **What V2 requires:** Mobile-optimized API endpoints returning Shot Card bundles with image/video URLs, candidate arrays, narrative context. Paginated shot-by-shot navigation. Progressive loading (visual first, audio async).
- **Effort:** MEDIUM
- **Dependencies:** GAP-2.1

#### GAP-3.4: AI Audit Extension Interface
- **What exists:** `AI_AUDIT` disposition in `Disposition` enum. In `reviews.py`, AI_AUDIT routes to APPROVING state identically to HUMAN. No scoring, no model registry, no feedback loop.
- **What V2 requires:** Scoring plugin bus (receive Shot Card, return multi-dimensional score vector). Model registry (version, capability tags, confidence thresholds). Feedback loop (human review results -> training signal). A/B test interface. Shadow mode (score without affecting decisions). Circuit breaker (auto-fallback to human on divergence). Phase 0 implementation: empty vector, fallback to human, shadow mode recording.
- **Effort:** LARGE (full implementation) / MEDIUM (Phase 0 stub)
- **Dependencies:** GAP-2.1 (Shot Card as input format)

#### GAP-3.5: Video/Media Preview Infrastructure
- **What exists:** `content_ref` is a string reference. `metadata_json` may contain base64-encoded preview images (used in Telegram bot). No video playback, no frame-by-frame viewer, no media serving.
- **What V2 requires:** Media serving/streaming infrastructure. Video playback endpoints. Frame extraction. Thumbnail generation. Candidate comparison views. CDN/proxy for media files from OpenClaw storage.
- **Effort:** MEDIUM
- **Dependencies:** GAP-2.1, external storage integration

---

## Layer 4: Audit Data Layer

### V2 Requirement

Tiered storage: hot (PostgreSQL/TimescaleDB, 30-day rolling), warm (S3/MinIO object storage, 1-year), cold (WORM/Glacier, permanent). Desktop audit cockpit (timeline view, statistics, diff mode). Mobile audit dashboard.

### Current V1 State

| Aspect | V1 Implementation | V2 Requirement |
|--------|------------------|----------------|
| Primary database | SQLite WAL mode. Single file at `./data/review.db`. `aiosqlite` async driver. SQLAlchemy 2.0 async engine. PRAGMA: WAL, busy_timeout=5000, foreign_keys=ON. | PostgreSQL + TimescaleDB for hot storage (30-day rolling). Complex queries, aggregations, time-series analytics. |
| Schema | 4 tables: `reviews`, `audit_entries`, `policy_versions`, `webhook_configs`. No partitioning, no time-series optimization. | TimescaleDB hypertables for audit data. Partitioned by time. Separate hot/warm/cold tiers. |
| Immutable storage | SQLite authorizer blocks UPDATE/DELETE on `audit_entries`. SHA-256 hash chain per review. | WORM storage for permanent compliance archive. Merkle Root anchoring to Git. |
| Object storage | None. All data in SQLite. | S3/MinIO for warm storage (JSONL archives). Glacier/WORM for cold storage. |
| Audit analytics | None. Raw audit entries queryable by review_id. No aggregation, no statistics, no timeline view. | Desktop audit cockpit with timeline visualization, statistical panels, policy diff mode, rejection attribution analysis. |
| Mobile audit | Telegram `/status` command returns pending count. | Full mobile audit dashboard (review waterfall, detail pages, management). |
| Data lifecycle | No retention policy. Data accumulates in SQLite indefinitely. | 30-day hot -> 1-year warm -> permanent cold. Automated migration between tiers. |

### Gaps

#### GAP-4.1: Database Migration (SQLite -> PostgreSQL/TimescaleDB)
- **What exists:** SQLite WAL with aiosqlite. `create_async_engine("sqlite+aiosqlite:///./data/review.db")`. SQLite-specific PRAGMAs. SQLite authorizer for audit immutability.
- **What V2 requires:** PostgreSQL with TimescaleDB extension. `asyncpg` or `psycopg` async driver. Hypertable configuration for audit_entries. Migration scripts. Updated SQLAlchemy engine config. Removal of SQLite-specific code (PRAGMAs, authorizer).
- **Effort:** LARGE -- touches every database interaction, config, docker-compose, migrations
- **Dependencies:** PostgreSQL infrastructure (new container in docker-compose), asyncpg driver

#### GAP-4.2: Tiered Storage Architecture
- **What exists:** Single SQLite database file, bind-mounted from host.
- **What V2 requires:** Hot tier (PostgreSQL/TimescaleDB, 30-day). Warm tier (S3/MinIO, JSONL archives, 1-year). Cold tier (WORM/Glacier, permanent). Automated lifecycle policies. Archive workers.
- **Effort:** LARGE
- **Dependencies:** GAP-4.1, MinIO/S3 infrastructure

#### GAP-4.3: Audit Cockpit (Desktop Analytics)
- **What exists:** Dashboard shows review list with approve/reject actions. No analytics, no timeline, no statistics, no diff views.
- **What V2 requires:** Timeline visualization of review decisions. Statistical panels (approval rates, rejection reasons, policy effectiveness). Policy version diff mode (compare decisions under old vs new policy). Rejection reason attribution analysis.
- **Effort:** MEDIUM
- **Dependencies:** GAP-4.1 (PostgreSQL for complex queries), GAP-2.1 (Shot Card context)

#### GAP-4.4: Mobile Audit Dashboard
- **What exists:** Telegram bot `/status` returns pending count only.
- **What V2 requires:** PWA audit pages: dashboard with stats, review waterfall (timeline), detail pages with full Shot Card context, management pages for policy/workflow review.
- **Effort:** MEDIUM
- **Dependencies:** GAP-3.2 (PWA infrastructure), GAP-2.1

#### GAP-4.5: Data Lifecycle Management
- **What exists:** No retention policy. `check_timeouts` cron manages review state timeouts but not data lifecycle.
- **What V2 requires:** Automated archival worker: hot -> warm migration after 30 days. Warm -> cold migration after 1 year. arq cron jobs for lifecycle management. Configurable retention policies.
- **Effort:** MEDIUM
- **Dependencies:** GAP-4.1, GAP-4.2

---

## Cross-Cutting Concerns

### GAP-CC.1: OpenClaw Integration
- **What exists:** None. The platform is standalone. `source_system` field identifies the caller but there is no pipeline integration.
- **What V2 requires:** Bidirectional integration with OpenClaw execution engine. Receive DAG events (node completion, errors). Send ResumeCommands after approval. Issue Capability Tokens for downstream execution. Track workflow versions. Listen to OpenClaw event bus.
- **Effort:** LARGE (depends on OpenClaw API availability)
- **Dependencies:** External OpenClaw system

### GAP-CC.2: Authentication & Authorization Expansion
- **What exists:** JWT-based API auth (`client_id` claim). One-time review tokens (Redis, 72h TTL). Cookie-based web auth. Telegram bot chat ID allowlist.
- **What V2 requires:** Multi-role auth: admin (policy management), reviewer (desktop/mobile), auditor (read-only analytics), AI service (scoring). Per-project permissions. Reviewer workload assignment. Capability Token scoping.
- **Effort:** MEDIUM
- **Dependencies:** None

### GAP-CC.3: Docker Compose Expansion
- **What exists:** 4 containers: API (python:3.12-slim, 256MB), Nginx (alpine, 32MB), Redis (7-alpine, 64MB), Dozzle (optional monitoring, 32MB). Total ~384MB.
- **What V2 requires:** Additional containers: PostgreSQL (128-256MB), MinIO (128MB). This exceeds the 400MB total constraint in CLAUDE.md. Requires either relaxed constraints or architectural compromises.
- **Effort:** MEDIUM
- **Dependencies:** GAP-4.1, GAP-4.2, infrastructure capacity

### GAP-CC.4: Configuration Expansion
- **What exists:** `Settings` class with: `api_key`, `jwt_secret`, `redis_url`, `database_url`, `log_level`, `host`, `port`, `telegram_bot_token`, `telegram_allowed_chat_ids`, `review_timeout_minutes`.
- **What V2 requires:** Additional config: `git_repo_url`, `git_branch`, `postgres_url` (replace `database_url`), `minio_endpoint`, `minio_access_key`, `minio_secret_key`, `s3_bucket`, `openclaw_event_url`, `capability_token_secret`, retention policy settings, PWA settings.
- **Effort:** SMALL
- **Dependencies:** GAP-1.1, GAP-4.1, GAP-4.2

### GAP-CC.5: Requirements / Dependencies Update
- **What exists:** `requirements.txt` with FastAPI, SQLAlchemy, aiosqlite, redis, arq, PyJWT, httpx, Jinja2 fragments, python-telegram-bot, etc.
- **What V2 requires:** Add: `asyncpg` (PostgreSQL async driver), `gitpython` or `pygit2` (Git integration), `minio` (S3 client). Remove: `aiosqlite` (replaced by asyncpg). Possibly add: `timescaledb` client libs, PWA build tools (if not CDN-only).
- **Effort:** SMALL
- **Dependencies:** GAP-1.1, GAP-4.1, GAP-4.2

---

## Dependency Graph

```
Foundation Layer (no dependencies):
  GAP-2.1  Shot Card Data Model
  GAP-CC.2 Auth Expansion
  GAP-CC.4 Config Expansion
  GAP-CC.5 Requirements Update

GitOps Layer (depends on foundation):
  GAP-1.1  Git Repository Integration
  GAP-1.5  Workflow Definition Versioning (depends on GAP-1.1 + OpenClaw)

Core Engine Layer (depends on Shot Card model):
  GAP-2.3  Enhanced Policy Engine (depends on GAP-1.1, GAP-2.1)
  GAP-2.5  Approval Router (depends on GAP-2.1, GAP-2.2)
  GAP-2.6  Capability Tokens (depends on GAP-2.4)
  GAP-2.7  Enhanced Audit Recorder (depends on GAP-4.1, GAP-2.1)
  GAP-2.8  Event Bus Enhancements (depends on GAP-2.1, GAP-2.2)

  Heavy Engine (depends on Shot Card + OpenClaw):
  GAP-2.2  Shot Card Aggregator (depends on GAP-2.1, GAP-2.8, OpenClaw)
  GAP-2.4  Checkpoint Manager (depends on GAP-2.1, GAP-2.2, OpenClaw)
  GAP-2.9  Topology Collapser (depends on GAP-2.1, GAP-2.2, OpenClaw)

Provenance Layer (depends on GitOps + Shot Card):
  GAP-1.2  Policy-as-Code (depends on GAP-1.1)
  GAP-1.3  Provenance Tracking (depends on GAP-1.1, GAP-2.1)
  GAP-1.4  Merkle Root Anchoring (depends on GAP-4.2)
  GAP-1.6  Shot Card Template Versioning (depends on GAP-1.1, GAP-2.1)

Data Layer (foundational infra):
  GAP-4.1  PostgreSQL Migration (standalone)
  GAP-4.2  Tiered Storage (depends on GAP-4.1)
  GAP-4.5  Data Lifecycle (depends on GAP-4.1, GAP-4.2)

UI Layer (depends on Shot Card + Engine):
  GAP-3.1  Desktop Workstation (depends on GAP-2.1, GAP-2.2)
  GAP-3.2  Mobile PWA (depends on GAP-2.1)
  GAP-3.3  Mobile API (depends on GAP-2.1)
  GAP-3.4  AI Audit Interface (depends on GAP-2.1)
  GAP-3.5  Media Preview (depends on GAP-2.1)

Analytics Layer (depends on Data + Shot Card):
  GAP-4.3  Audit Cockpit (depends on GAP-4.1, GAP-2.1)
  GAP-4.4  Mobile Audit Dashboard (depends on GAP-3.2, GAP-2.1)

Infrastructure:
  GAP-CC.1 OpenClaw Integration (external dependency)
  GAP-CC.3 Docker Compose Expansion (depends on GAP-4.1, GAP-4.2)
```

---

## Effort Summary

| Effort | Count | Gaps |
|--------|-------|------|
| SMALL | 5 | GAP-1.3, GAP-1.5(partial), GAP-1.6, GAP-CC.4, GAP-CC.5 |
| MEDIUM | 10 | GAP-1.1, GAP-1.2, GAP-1.4, GAP-2.3, GAP-2.5, GAP-2.6, GAP-2.8, GAP-3.3, GAP-3.5, GAP-4.3, GAP-4.4, GAP-4.5, GAP-CC.2, GAP-CC.3 |
| LARGE | 9 | GAP-2.1, GAP-2.2, GAP-2.4, GAP-2.7, GAP-2.9, GAP-3.1, GAP-3.2, GAP-3.4, GAP-4.1, GAP-4.2, GAP-CC.1 |

---

## What V1 Does Well (Reusable Assets)

These V1 components are well-built and can be extended rather than replaced:

1. **State Machine** (`app/core/state_machine.py`) -- Optimistic locking pattern is sound. Can be extended to handle Shot Card states and more granular transitions.

2. **Policy Engine** (`app/core/policy.py`) -- YAML + JSON Schema validation + AND/OR evaluation is solid. Can be enhanced to accept Shot Card input and support policy stacking.

3. **Audit Logger** (`app/core/audit.py`) -- SHA-256 hash chain with SQLite authorizer. Merkle Root can be built on top of this foundation.

4. **Event Manager** (`app/core/events.py`) -- asyncio.Queue-based SSE with broadcast and slow-client eviction. Progressive fill events can be added to the same pipeline.

5. **Token Service** (`app/core/auth.py`) -- JWT + one-time Redis tokens with Lua atomic consume. Capability Tokens extend the same pattern.

6. **Webhook Delivery** (`app/workers/tasks.py`) -- arq-based retry with exponential backoff and HMAC signatures. Robust pattern for all outbound integrations.

7. **Timeout Management** (`app/workers/tasks.py`) -- Cron-based timeout escalation and reminder notifications. Pattern extends to per-route-type timeouts.

8. **Gold Team Integration** (`app/integrations/gold_team/client.py`) -- Async client with risk-tier mapping. Pattern demonstrates how external systems submit to the platform.

9. **Telegram Bot** (`app/bot/handlers.py`) -- Notification + inline action pattern works. V2 may keep Telegram as a secondary notification channel alongside PWA.

---

## Recommended Migration Sequence

Given the dependency graph, a phased migration is recommended:

**Phase A: Foundation (GAP-2.1 + GAP-CC.4 + GAP-CC.5)**
- Define Shot Card data model alongside existing Review model
- Expand configuration
- Update requirements
- Dual-write: keep Review model working, add Shot Card as new layer

**Phase B: GitOps (GAP-1.1 + GAP-1.2 + GAP-1.3)**
- Git repo integration for policies
- Policy-as-code workflow
- Provenance tracking on Shot Cards

**Phase C: Engine Core (GAP-2.3 + GAP-2.5 + GAP-2.8)**
- Enhanced policy engine
- Approval router
- Event bus enhancements

**Phase D: Database Migration (GAP-4.1 + GAP-CC.3)**
- PostgreSQL migration
- Docker Compose update
- This is a high-risk inflection point -- requires careful data migration

**Phase E: Aggregation (GAP-2.2 + GAP-2.9 + GAP-CC.1)**
- Shot Card aggregator
- Topology collapser
- OpenClaw integration

**Phase F: UI Rebuild (GAP-3.1 + GAP-3.2 + GAP-3.3)**
- Desktop workstation
- Mobile PWA
- Mobile API

**Phase G: Advanced (GAP-2.4 + GAP-2.6 + GAP-3.4 + GAP-4.2)**
- Checkpoint manager
- Capability tokens
- AI audit Phase 0
- Tiered storage

---

## Constraint Conflict: Memory Budget

V1 CLAUDE.md specifies **Docker container total memory < 400MB**. Current V1 uses ~384MB (API 256 + Nginx 32 + Redis 64 + Dozzle 32).

V2 requires PostgreSQL (~128-256MB) and potentially MinIO (~128MB), which would push total to ~700-800MB. This conflicts with the stated constraint.

**Options:**
1. Relax constraint to 1GB (8GB machine can support this)
2. Use external PostgreSQL instance (separate machine)
3. Use managed PostgreSQL (cloud, but contradicts LAN-only deployment)
4. Optimize container sizes aggressively (Alpine-based Postgres, reduce API memory)
5. Use SQLite with time-series extensions instead of PostgreSQL/TimescaleDB

This constraint conflict must be resolved before Phase D (Database Migration) begins.
