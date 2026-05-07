# Phase 11: kais-movie-agent Integration - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Movie-agent pipeline review gates use the remote review platform instead of local interactive review, with automatic resume or rollback. This phase creates a Node.js ReviewPlatformClient in the movie-agent repo, replaces `_runReview()` in pipeline.js with remote review submission, adds a callback HTTP server for receiving approval/rejection results, and sends material preview images via Telegram photo messages.

Requirements: MA-01, MA-02, MA-03, MA-04, MA-05, MA-06, MA-07

</domain>

<decisions>
## Implementation Decisions

### Client Module & Auth
- Client module lives in movie-agent repo: `lib/review-platform-client.js` — Node.js cannot share Python integration pattern (consistent with STATE.md GT-10 decision)
- Native `fetch` for HTTP calls (Node 18+, zero dependencies) — matches existing dependency tree constraint
- API key exchange for JWT with 60s cache safety margin — same pattern as gold-team integration
- Fail-open on review submission failure: if review platform unreachable, task proceeds without review (logged warning, consistent with GT-10 decision)

### Review Gate Replacement
- New `_runRemoteReview()` in pipeline.js submits to review platform, saves pipeline state with review_id, then exits — pipeline resumes later via callback (no long-running process)
- Flatten multi-candidate reviews into single review submission with candidate metadata in content_ref — approve=continue, reject=rollback. Multi-candidate selection (scoring, ranking, feedback) deferred to future enhancement
- All review gates go remote: art-direction, character, voice, scene, storyboard, camera — all phases with `review: {...}` config in PHASES array

### Callback & Resume
- Callback server: lightweight `node:http` server in `bin/callback-server.js` — no framework, matches existing minimal pattern
- Callback handler spawns `pipeline.resume(phaseId)` as child process via GitStageManager — clean process isolation
- Rejection: `GitStageManager.rollback(stage)` to previous checkpoint, pipeline state stays `failed` — user re-runs phase after fixing material

### Material Preview Images (MA-07)
- Base64-encode images in review submission metadata — review platform Bot reads them and sends via Telegram `sendPhoto` API
- Max 3 preview images per review (cover image + up to 2 candidate thumbnails) — keeps Telegram messages readable, avoids rate limits
- Visual phases send actual renders/scene images; audio phases (voice) send placeholder image with "audio preview" text

### Claude's Discretion
- Exact client API surface (method signatures, error types)
- Callback server port configuration and HMAC verification details
- Pipeline state file format for review_id persistence
- Test strategy (unit vs integration split)
- Image size optimization before base64 encoding

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (Review Platform)
- `app/integrations/gold_team/client.py` — Python client pattern: ReviewPlatformClient with JWT auth, submit_gpu_review(), query_review_status(), risk score computation, fail-open behavior
- `app/api/v1/reviews.py` — POST /api/v1/reviews (submit), GET /api/v1/reviews/{id} (query), ReviewCreateRequest schema with callback_url/callback_secret
- `app/models/schemas.py` — ReviewCreateRequest: type, content_ref, source_system, metadata, priority, risk_score, callback_url, callback_secret
- `app/bot/` — Telegram Bot with InlineKeyboard approve/reject, photo sending capability
- `app/workers/tasks.py` — deliver_review_callback arq task with HMAC signing, retry with backoff

### Reusable Assets (Movie Agent)
- `lib/pipeline.js` — Pipeline class with _runReview(), runPhase(), resume(), _loadState()/_saveState(), PHASES array (7 review gates)
- `lib/interactive-review.js` — Current local review: createReviewSession(), addReviewItems(), generateReviewPage(), node:http server for submission
- `lib/git-stage-manager.js` — GitStageManager with checkpoint(), rollback() per stage
- `lib/hooks/` — Phase-specific hooks for before/after processing

### Established Patterns
- Review platform API: POST /api/v1/reviews with source_system, type, metadata, callback_url, callback_secret
- Callback delivery: HMAC-SHA256 signed POST to callback_url with retry (1s/5s/30s)
- Pipeline state: JSON file `.pipeline-state.json` with phases, currentPhaseId, status per phase
- Git checkpoints: one per stage, rollback restores files to checkpoint state
- Risk scoring: HIGH_RISK_TYPES (0.8), LOW_RISK_TYPES (0.2), unknown (0.5)

### Integration Points
- Review platform API at http://192.168.71.140:8090 — movie-agent submits reviews here
- callback_url in review submission → movie-agent's callback-server.js receives result
- Pipeline._runReview() → replace with _runRemoteReview() that calls ReviewPlatformClient
- Pipeline state file → persist review_id for callback-to-resume mapping
- GitStageManager.rollback() → called on rejection callback
- Telegram Bot → needs to handle image sending for movie-agent review notifications

</code_context>

<specifics>
## Specific Ideas

- Movie-agent runs on 192.168.71.38 (worker machine), review platform on 192.168.71.140
- Pipeline PHASES with review config: art-direction, character, voice, scene, storyboard, camera (6 gates, not 7 — some have review:false)
- Current _runReview() spawns node:http server, serves HTML page, waits for browser submission
- Git checkpoint per stage with file glob patterns in STAGE_REGISTRY
- Pipeline already has resume(fromPhaseId) method — can be triggered by callback
- callback_data format: approve/reject:review_id:version (from Phase 09)

</specifics>

<deferred>
## Deferred Ideas

- Multi-candidate selection UI (scoring, ranking, comparative feedback) — current review platform only supports approve/reject
- Automatic material regeneration on rejection — user must manually fix and re-run
- Parallel review gates (submit multiple phases for review simultaneously)
- Audio clip preview in Telegram (file attachment instead of placeholder image)

</deferred>
