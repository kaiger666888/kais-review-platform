# Roadmap: Kai's Review Platform V2

## Milestones

- [x] **v1.0** — Policy-driven review governance platform — [archived](milestones/v1.0-ROADMAP.md)
- [x] **v1.1** — Integration tests & tech debt — [archived](milestones/v1.1-ROADMAP.md)
- [x] **v1.2** — External system integration — [see below]
- [ ] **v2.0** — Shot Card-driven pipeline governance platform — Phases 15-22

## Phases

<details>
<summary>v1.0+v1.1 (Phases 01-07) — Shipped</summary>

- [x] Phase 01: Core Engine (5/5 plans)
- [x] Phase 02: Real-time Events (2/2 plans)
- [x] Phase 03: Review Frontend (3/3 plans)
- [x] Phase 04: Deployment & Hardening (2/2 plans)
- [x] Phase 05: Tech Debt Fixes (2/2 plans)
- [x] Phase 06: API + Event Integration Tests (3/3 plans)
- [x] Phase 07: Docker Stack Integration Tests (1/1 plan)

</details>

<details>
<summary>v1.2 External System Integration (Phases 08-14)</summary>

- [x] Phase 08: Schema & Callback Infrastructure (2/2 plans) — completed 2026-05-07
- [x] Phase 09: Telegram Review Bot (2/2 plans) — completed 2026-05-07
- [x] Phase 10: kais-gold-team Integration (2/2 plans) — completed 2026-05-07
- [x] Phase 11: kais-movie-agent Integration (2/2 plans) — completed 2026-05-07
- [x] Phase 12: Dual Bot Coordination & E2E (2/2 plans) — completed 2026-05-08
- [ ] Phase 13: Cross-System Protocol Alignment (0/2 plans)
- [ ] Phase 14: E2E Callback Verification (0/1 plan)

</details>

## Active Milestone

**v2.0 Architecture Rewrite** — Phases 15-22

Full rewrite from generic review queue to Shot Card-driven pipeline governance platform. PostgreSQL replaces SQLite, GitOps version control for policies, desktop 3-column workstation + mobile PWA card flow dual-frontend, AI audit Phase 0 stubs, tiered storage, Merkle Root audit anchoring.

- [x] **Phase 15: Foundation** — Shot Card data model, PostgreSQL migration, Docker Compose expansion, config & dependency updates (completed 2026-05-16)
- [ ] **Phase 16: Shot Card Aggregation** — Aggregator, topology collapser, progressive fill engine
- [ ] **Phase 17: GitOps Policy Engine** — Enhanced policy engine with Shot Card input, Git integration, provenance tracking
- [ ] **Phase 18: Routing & Checkpoints** — Approval router with priority queues, checkpoint manager with timeout escalation, event bus enhancements
- [ ] **Phase 19: AI Audit & Capability Tokens** — AI audit Phase 0 stubs, capability token issuance, model registry placeholders
- [ ] **Phase 20: Desktop Workstation** — 3-column UI, keyboard shortcuts, dual-column comparison, batch operations, candidate array, media preview
- [ ] **Phase 21: Mobile PWA** — Card flow layout, gesture controls, offline caching, mobile API endpoints
- [ ] **Phase 22: Audit & Compliance** — Merkle Root anchoring, dual-write audit recorder, tiered storage, data lifecycle, multi-role auth, audit cockpit dashboards

## Phase Details

### Phase 15: Foundation
**Goal**: The platform runs on PostgreSQL with a complete Shot Card data model, ready for all downstream engine and UI layers
**Depends on**: Nothing (first V2 phase, replaces V1 foundation)
**Requirements**: SHOT-01, DB-01, DB-04, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. A Shot Card can be created with all nested fields (narrative_context, visual_bundle, audio_bundle, audit_state, provenance) and retrieved with zero data loss
  2. PostgreSQL + TimescaleDB container runs in Docker Compose alongside existing containers, total memory stays under 1GB
  3. Application connects to PostgreSQL via asyncpg, all existing V1 integration tests pass against the new database (or V1 code is cleanly removed)
  4. Settings class loads git_repo_url, postgres_url, minio_endpoint, openclaw_event_url, capability_token_secret from environment
  5. requirements.txt includes asyncpg, gitpython, minio and excludes aiosqlite
**Plans:** 2/2 plans complete

Plans:
- [x] 15-01-PLAN.md — Shot Card data model (ShotCard + AuditEntry SQLAlchemy models, Pydantic schemas, PostgreSQL async engine, Alembic migration, TimescaleDB init) -- completed 2026-05-16
- [ ] 15-02-PLAN.md — Docker Compose expansion + config/dependency updates (PostgreSQL + MinIO containers, V2 Settings, requirements.txt, Dockerfile, start.sh)

### Phase 16: Shot Card Aggregation
**Goal**: Node outputs from an AI pipeline progressively assemble into Shot Cards, with visual bundles displaying first and audio appending when ready
**Depends on**: Phase 15 (Shot Card model and PostgreSQL)
**Requirements**: SHOT-02, SHOT-03, SHOT-04
**Success Criteria** (what must be TRUE):
  1. An OpenClaw node completion event (mock) triggers aggregation into the correct Shot Card by shot_id, even when nodes complete out of order (video before image)
  2. Visual bundle fields appear on the Shot Card as soon as their source nodes complete; audio bundle fields append independently without blocking visual review
  3. The min_audit_set logic unlocks a Shot Card for review only when all required bundles are populated, and the unlock state is queryable via API
**Plans:** 2 plans

Plans:
- [ ] 16-01-PLAN.md — Event types, topology collapser, progressive fill engine, aggregator orchestrator (SHOT-03, SHOT-04)
- [ ] 16-02-PLAN.md — Shot Card API endpoints, arq task registration, aggregation pipeline tests (SHOT-02, SHOT-03, SHOT-04)

### Phase 17: GitOps Policy Engine
**Goal**: Policy decisions are driven by Git-versioned rule files, with every Shot Card carrying the exact policy commit SHA that evaluated it
**Depends on**: Phase 15 (Shot Card model), Phase 16 (aggregator for test data)
**Requirements**: POL-01, POL-02, POL-03
**Success Criteria** (what must be TRUE):
  1. Policy engine accepts a Shot Card as input and returns a routing decision (AUTO/HUMAN/AI_AUDIT/BLOCK) using narrative_context fields like continuity_tags and emotion_curve
  2. Multiple policies (global + project + temporary) are evaluated in stacked order with deterministic precedence, and the effective policy is logged
  3. Every Shot Card stores policy_commit_sha, workflow_version, and execution_id in its provenance field, and these are queryable in audit records
  4. Policy YAML files are read from a Git repo at a specific commit SHA, and changes to policy files in the repo are reflected on next evaluation without application restart
**Plans**: TBD

Plans:
- [ ] 17-01: Enhanced policy engine (Shot Card input, policy stacking, narrative context)
- [ ] 17-02: Git integration for policy-as-code + provenance tracking

### Phase 18: Routing & Checkpoints
**Goal**: Shot Cards are dynamically routed to the correct review outlet with priority ordering, and pipeline execution state is preserved for resume after approval
**Depends on**: Phase 15 (Shot Card model), Phase 17 (policy engine for routing decisions)
**Requirements**: ROUT-01, CHKP-01, CHKP-02, EVT-01
**Success Criteria** (what must be TRUE):
  1. A Shot Card evaluated as HUMAN routes to the desktop queue; a Shot Card evaluated as AI_AUDIT routes to the AI outlet; AUTO Shot Cards are approved immediately without human intervention
  2. High-priority Shot Cards (GPU renders) are dequeued before low-priority ones (preview cards), and a batch of same-scene Shot Cards can be approved in a single operation
  3. OpenClaw execution state is serialized as a RunState Snapshot in Redis, and after approval a ResumeCommand is produced that a mock execution layer can consume to resume
  4. A Shot Card in human review for 24 hours is automatically rejected; a Shot Card in AI review for 5 minutes is escalated to human review
  5. Event bus emits node_completed, bundle_ready, and shot_card_updated events, and each outlet (desktop/mobile) receives only its targeted events
**Plans**: TBD

Plans:
- [ ] 18-01: Approval router with priority queues + batch approval
- [ ] 18-02: Checkpoint manager (RunState snapshots, ResumeCommand, timeout escalation)
- [ ] 18-03: Event bus enhancements (progressive fill events, per-outlet routing)

### Phase 19: AI Audit & Capability Tokens
**Goal**: AI audit interfaces exist as verified stubs returning empty vectors with shadow-mode recording, and capability tokens gate downstream GPU execution after approval
**Depends on**: Phase 15 (Shot Card model), Phase 18 (routing for AI_AUDIT outlet)
**Requirements**: ROUT-02, AI-01, AI-02, AI-03, AI-04, AI-05
**Success Criteria** (what must be TRUE):
  1. A Shot Card routed to AI_AUDIT receives an empty score vector from the scoring plugin bus, the system falls back to human review, and the empty score is recorded in audit
  2. Shadow mode runs AI scoring on all reviewed Shot Cards alongside human decisions, recording scores without affecting outcomes, and the scores are queryable later
  3. Model registry returns model_unavailable for all queries, and feedback data (human decisions) is written to cold storage for future training
  4. After a Shot Card is approved, a capability token is issued encoding authorized node scope, and a verification endpoint confirms or rejects the token
  5. A/B test interface accepts a batch of Shot Cards and produces paired records (AI score + human decision) in a dedicated data structure, queryable by batch_id
**Plans**: TBD

Plans:
- [ ] 19-01: AI audit Phase 0 (scoring bus, shadow mode, model registry, feedback loop, A/B interface)
- [ ] 19-02: Capability token issuance + verification endpoint

### Phase 20: Desktop Workstation
**Goal**: Reviewers use a 3-column desktop workstation to efficiently review Shot Cards with keyboard shortcuts, media playback, comparisons, and batch operations
**Depends on**: Phase 15 (Shot Card model), Phase 16 (aggregated data), Phase 18 (routing + events)
**Requirements**: UI-D-01, UI-D-02, UI-D-03, UI-D-04, UI-D-05, MEDIA-01, MEDIA-02, MEDIA-03
**Success Criteria** (what must be TRUE):
  1. The desktop UI displays three columns: left panel with filterable/sortable shot queue (by project, scene, risk level), center panel with Shot Card preview (video player + frame viewer + candidate thumbnails), right panel with narrative context + prompt summary + node status + decision buttons
  2. Reviewer can navigate entirely by keyboard: Space plays/pauses video, Y approves, N rejects, J/K moves between shots, D opens diff view, B enters batch mode, G opens Git policy view
  3. Dual-column comparison shows first-frame vs last-frame, current candidate vs history, or current vs reference image, switchable within the center panel
  4. Multiple Shot Cards can be selected via Ctrl/Shift in the left panel and approved, rejected, or suspended in a single batch action
  5. Video playback streams from a media endpoint with timeline scrubbing; first/last frame thumbnails are auto-generated; candidate thumbnails in a grid allow one-click switching between draw results
**UI hint**: yes
**Plans**: TBD

Plans:
- [ ] 20-01: 3-column layout + shot queue panel + decision panel
- [ ] 20-02: Media preview infrastructure (video streaming, frame extraction, thumbnails)
- [ ] 20-03: Keyboard shortcuts + dual-column comparison + batch operations + candidate array

### Phase 21: Mobile PWA
**Goal**: Reviewers can approve or reject Shot Cards on mobile with swipe gestures, even when offline, seeing narrative continuity between shots
**Depends on**: Phase 15 (Shot Card model), Phase 16 (aggregated data), Phase 18 (routing + events)
**Requirements**: UI-M-01, UI-M-02, UI-M-03, UI-M-04, UI-M-05
**Success Criteria** (what must be TRUE):
  1. Mobile PWA displays Shot Cards as a vertical swipeable card flow (shot-to-shot navigation maintaining narrative continuity) with horizontal swipe for candidate switching within the same shot
  2. Swipe left approves, swipe right rejects, swipe up reveals detail (prompts, audio params), pinch-to-zoom enlarges frames, and a context bar at the top shows scene, shot number, and emotion curve
  3. Service Worker caches the 20 most recent Shot Cards and manifest.json enables install-to-homescreen; the app loads cached cards when offline
  4. Mobile API endpoint returns Shot Card bundles (visual + audio + narrative) paginated shot-by-shot with progressive loading (visual first, audio async)
**UI hint**: yes
**Plans**: TBD

Plans:
- [ ] 21-01: Mobile API endpoints (Shot Card bundles, paginated shot-by-shot)
- [ ] 21-02: PWA card flow (layout, gestures, context bar, offline cache, manifest)

### Phase 22: Audit & Compliance
**Goal**: Every decision is tamper-evident via Merkle Root anchoring, tiered storage manages data lifecycle automatically, and multi-role auth controls access across the platform
**Depends on**: Phase 15 (PostgreSQL), Phase 17 (provenance), Phase 20 (desktop audit cockpit), Phase 21 (mobile audit pages)
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04, AUTH-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):
  1. Daily Merkle Root is computed from all audit entries and committed to the Git repo; a verification endpoint detects any tampering by recomputing the tree
  2. Audit records are written to PostgreSQL in real-time and asynchronously archived to MinIO as JSONL, queryable from both tiers
  3. arq cron workers automatically move audit records from hot storage (PostgreSQL, 30d) to warm storage (MinIO, 1yr) to cold storage (WORM, permanent) based on configurable retention policies
  4. Users with admin role can manage policies, reviewer role can access desktop/mobile review, auditor role has read-only analytics access, and ai_service role can submit scores -- each role sees only authorized UI and API endpoints
  5. Desktop audit cockpit shows a timeline of review decisions, statistical panels (throughput, rejection reasons, policy hit rates), and policy version diff mode; mobile audit page shows dashboard stats and review history waterfall
**UI hint**: yes
**Plans**: TBD

Plans:
- [ ] 22-01: Merkle Root anchoring + dual-write audit recorder + tiered storage lifecycle
- [ ] 22-02: Multi-role authentication (admin, reviewer, auditor, ai_service)
- [ ] 22-03: Desktop audit cockpit + mobile audit dashboard

## Progress

**Execution Order:**
Phases execute in numeric order: 15 -> 16 -> 17 -> 18 -> 19 -> 20 -> 21 -> 22

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 15. Foundation | v2.0 | 0/2 | Complete    | 2026-05-16 |
| 16. Shot Card Aggregation | v2.0 | 0/2 | Not started | - |
| 17. GitOps Policy Engine | v2.0 | 0/2 | Not started | - |
| 18. Routing & Checkpoints | v2.0 | 0/3 | Not started | - |
| 19. AI Audit & Capability Tokens | v2.0 | 0/2 | Not started | - |
| 20. Desktop Workstation | v2.0 | 0/3 | Not started | - |
| 21. Mobile PWA | v2.0 | 0/2 | Not started | - |
| 22. Audit & Compliance | v2.0 | 0/3 | Not started | - |
