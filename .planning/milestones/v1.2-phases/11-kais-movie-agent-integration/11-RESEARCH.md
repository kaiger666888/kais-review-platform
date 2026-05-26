# Phase 11: kais-movie-agent Integration - Research

**Researched:** 2026-05-07
**Domain:** Node.js HTTP client integration, callback-driven pipeline pause/resume, Telegram photo messaging
**Confidence:** HIGH

## Summary

This phase integrates the movie-agent pipeline (Node.js, running on 192.168.71.38) with the review platform (Python/FastAPI, running on 192.168.71.140). The integration replaces the existing local interactive-review.js browser-based review system with remote review submission to the review platform. The movie-agent pipeline will submit reviews, save state with a review_id, and exit. A lightweight callback HTTP server receives approval/rejection results and triggers pipeline resume or rollback.

The key architectural shift is from synchronous in-process review (node:http server waiting for browser submission) to asynchronous callback-driven review (submit to platform, exit process, callback server spawns resume). The movie-agent already has all the building blocks: Pipeline class with resume(), GitStageManager with rollback(), and JSON state persistence. The integration layers a Node.js ReviewPlatformClient and a callback HTTP server on top.

**Primary recommendation:** Build three new modules in the movie-agent repo -- `lib/review-platform-client.js` (HTTP client), `bin/callback-server.js` (callback receiver), and modify `Pipeline._runReview()` to use remote review instead of local interactive-review.js. On the review platform side, extend the Telegram notification flow to support `sendPhoto` with base64 preview images from review metadata.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Client module lives in movie-agent repo: `lib/review-platform-client.js` -- Node.js cannot share Python integration pattern (consistent with STATE.md GT-10 decision)
- Native `fetch` for HTTP calls (Node 18+, zero dependencies) -- matches existing dependency tree constraint
- API key exchange for JWT with 60s cache safety margin -- same pattern as gold-team integration
- Fail-open on review submission failure: if review platform unreachable, task proceeds without review (logged warning, consistent with GT-10 decision)
- New `_runRemoteReview()` in pipeline.js submits to review platform, saves pipeline state with review_id, then exits -- pipeline resumes later via callback (no long-running process)
- Flatten multi-candidate reviews into single review submission with candidate metadata in content_ref -- approve=continue, reject=rollback. Multi-candidate selection (scoring, ranking, feedback) deferred to future enhancement
- All review gates go remote: art-direction, character, voice, scene, storyboard, camera -- all phases with `review: {...}` config in PHASES array
- Callback server: lightweight `node:http` server in `bin/callback-server.js` -- no framework, matches existing minimal pattern
- Callback handler spawns `pipeline.resume(phaseId)` as child process via GitStageManager -- clean process isolation
- Rejection: `GitStageManager.rollback(stage)` to previous checkpoint, pipeline state stays `failed` -- user re-runs phase after fixing material
- Base64-encode images in review submission metadata -- review platform Bot reads them and sends via Telegram `sendPhoto` API
- Max 3 preview images per review (cover image + up to 2 candidate thumbnails) -- keeps Telegram messages readable, avoids rate limits
- Visual phases send actual renders/scene images; audio phases (voice) send placeholder image with "audio preview" text

### Claude's Discretion
- Exact client API surface (method signatures, error types)
- Callback server port configuration and HMAC verification details
- Pipeline state file format for review_id persistence
- Test strategy (unit vs integration split)
- Image size optimization before base64 encoding

### Deferred Ideas (OUT OF SCOPE)
- Multi-candidate selection UI (scoring, ranking, comparative feedback) -- current review platform only supports approve/reject
- Automatic material regeneration on rejection -- user must manually fix and re-run
- Parallel review gates (submit multiple phases for review simultaneously)
- Audio clip preview in Telegram (file attachment instead of placeholder image)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MA-01 | Node.js HTTP client module (`ReviewPlatformClient`) for calling review-platform REST API (submit, query, auth) | Native fetch API (Node 24.13 verified), JWT auth via POST /api/v1/auth/token, same pattern as gold-team client.py |
| MA-02 | Pipeline review gates replaced: `interactive-review.js` submits to review-platform instead of launching local HTTP server | `_runRemoteReview()` replaces `_runReview()`, Pipeline class already has `_saveState()` for review_id persistence |
| MA-03 | Pipeline pauses after review submission, waiting for callback approval/rejection | Pipeline saves state with review_id + status "awaiting_review", then exits process. Callback server receives result later |
| MA-04 | movie-agent adds callback HTTP endpoint to receive approval/rejection results | `bin/callback-server.js` using node:http, HMAC-SHA256 verification via Node crypto module |
| MA-05 | On approval callback, pipeline auto-resumes to next phase | callback-server spawns `node pipeline.js resume <phaseId>` as child process, uses existing Pipeline.resume() |
| MA-06 | On rejection callback, pipeline rolls back to previous phase using existing git checkpoint mechanism | GitStageManager.rollback(previousStage) -- verified: reset --hard to checkpoint commit |
| MA-07 | Review notification includes material preview images (scene renders, storyboard frames) sent as Telegram photo messages | Base64 images in metadata, review platform Bot sends via python-telegram-bot sendPhoto API |
</phase_requirements>

## Standard Stack

### Core (Movie-Agent Side -- Node.js)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Node.js native `fetch` | 24.13.0 (verified) | HTTP client for review platform API | Zero dependencies, already available in runtime. CONTEXT.md locked decision |
| Node.js `node:http` | built-in | Callback HTTP server | No framework needed, matches existing minimal pattern in interactive-review.js and bin/git-stage.js |
| Node.js `node:crypto` | built-in | HMAC-SHA256 verification for callback signatures | Already used in movie-agent (randomUUID from crypto) |
| Node.js `node:fs/promises` | built-in | State persistence, image reading | Already used throughout movie-agent |

### Core (Review Platform Side -- Python)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-telegram-bot | 22.7.0 (verified) | Telegram Bot sendPhoto for preview images | Already installed, sendPhoto API available for base64 image sending |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Node.js `node:child_process` | built-in | Spawning pipeline resume as child process | callback-server.js spawns resume process |
| Node.js `node:path` | built-in | File path resolution | Image file reading for base64 encoding |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Native fetch | axios | axios would add dependency to movie-agent which has zero npm dependencies currently -- rejected per CONTEXT.md |
| Native fetch | got | Same dependency issue, got is heavier, native fetch is sufficient |
| node:http callback server | Express | Overkill for single-endpoint callback server, adds dependency, rejected per CONTEXT.md |
| Base64 in metadata | multipart file upload | Would require changes to ReviewCreateRequest schema and file upload endpoint -- base64 is simpler, 3-image limit keeps payload manageable |

**Installation:**
```bash
# No new packages needed -- all Node.js built-in APIs
# Review platform already has python-telegram-bot 22.7.0
```

**Version verification:**
```bash
$ node --version
v24.13.0
$ node -e "console.log(typeof fetch)"
function  # native fetch confirmed
$ node -e "const crypto = require('crypto'); console.log(typeof crypto.createHmac)"
function  # HMAC support confirmed
```

## Architecture Patterns

### Recommended Project Structure (Movie-Agent)
```
kais-movie-agent/
├── lib/
│   ├── review-platform-client.js   # NEW: ReviewPlatformClient class
│   ├── pipeline.js                  # MODIFY: _runReview -> _runRemoteReview
│   ├── interactive-review.js        # KEEP: not deleted, just no longer called by pipeline
│   ├── git-stage-manager.js         # KEEP: rollback mechanism for rejection
│   └── phases/
│       └── index.js                 # KEEP: phase handlers unchanged
├── bin/
│   ├── callback-server.js           # NEW: lightweight HTTP callback receiver
│   └── git-stage.js                 # KEEP: existing CLI tool
```

### Pattern 1: ReviewPlatformClient (Node.js, mirrors Python gold-team client)
**What:** Singleton HTTP client class with JWT auth, submit, and query methods.
**When to use:** Every review gate in the pipeline calls this client.
**Example:**
```javascript
// Source: Pattern from app/integrations/gold_team/client.py (Python)
// Adapted for Node.js with native fetch

export class ReviewPlatformClient {
  constructor({ baseUrl = 'http://192.168.71.140:8090', apiKey = '', timeout = 10000 } = {}) {
    this._baseUrl = baseUrl.replace(/\/$/, '');
    this._apiKey = apiKey;
    this._timeout = timeout;
    this._token = null;
    this._tokenExpires = 0;
  }

  async _ensureToken() {
    if (this._token && Date.now() < this._tokenExpires) return this._token;
    const resp = await fetch(`${this._baseUrl}/api/v1/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: this._apiKey, client_id: 'kais-movie-agent' }),
      signal: AbortSignal.timeout(this._timeout),
    });
    if (!resp.ok) throw new Error(`Auth failed: ${resp.status}`);
    const { data } = await resp.json();
    this._token = data.access_token;
    // 60s safety margin before expiry (same as gold-team)
    this._tokenExpires = Date.now() + (data.expires_in - 60) * 1000;
    return this._token;
  }

  async submitReview({ type, contentRef, metadata, callbackUrl, callbackSecret, priority, riskScore }) {
    const token = await this._ensureToken();
    const body = {
      type,
      content_ref: contentRef,
      source_system: 'kais-movie-agent',
      metadata,
      priority: priority || 'normal',
      risk_score: riskScore ?? 0.5,
    };
    if (callbackUrl) body.callback_url = callbackUrl;
    if (callbackSecret) body.callback_secret = callbackSecret;

    const resp = await fetch(`${this._baseUrl}/api/v1/reviews`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this._timeout),
    });
    if (!resp.ok) throw new Error(`Submit failed: ${resp.status}`);
    const { data } = await resp.json();
    return { reviewId: data.review_id, state: data.state, routing: data.routing };
  }
}
```

### Pattern 2: Callback-Driven Pipeline Pause/Resume
**What:** Pipeline submits review, saves state with review_id, exits process. Callback server receives result and spawns resume.
**When to use:** Every review gate in the pipeline.
**Example:**
```javascript
// Pipeline._runRemoteReview() replaces _runReview()
async _runRemoteReview(phase, phaseConfig = {}) {
  const client = new ReviewPlatformClient({ apiKey: this.config.reviewApiKey });

  // Collect preview images (max 3, base64 encoded)
  const previewImages = await this._collectPreviewImages(phase, phaseConfig);

  const result = await client.submitReview({
    type: 'pipeline_phase',
    contentRef: `${this.episode}:${phase.id}`,
    metadata: {
      phase_name: phase.name,
      phase_id: phase.id,
      stage_order: phase.stageOrder,
      episode: this.episode,
      preview_images: previewImages,  // base64 strings
    },
    callbackUrl: this.config.callbackUrl,
    callbackSecret: this.config.callbackSecret,
  });

  // Save state with review_id and exit
  const state = await this._loadState();
  state.phases[phase.id] = {
    status: 'awaiting_review',
    review_id: result.reviewId,
    submitted_at: new Date().toISOString(),
  };
  await this._saveState(state);

  // Return special sentinel -- caller must exit process
  return { action: 'awaiting_review', review_id: result.reviewId };
}
```

### Pattern 3: Callback Server (bin/callback-server.js)
**What:** Minimal node:http server that receives HMAC-signed callbacks and spawns pipeline resume/rollback.
**When to use:** Runs as a separate process on 192.168.71.38 to receive review results.
**Example:**
```javascript
// bin/callback-server.js -- lightweight callback receiver
import { createServer } from 'node:http';
import { createHmac } from 'node:crypto';
import { execFile } from 'node:child_process';

const CALLBACK_SECRET = process.env.REVIEW_CALLBACK_SECRET || '';
const PORT = parseInt(process.env.CALLBACK_PORT || '8766', 10);
const WORKDIR = process.env.PIPELINE_WORKDIR || process.cwd();

function verifyHmac(body, signature) {
  if (!CALLBACK_SECRET) return true; // Dev mode
  const expected = createHmac('sha256', CALLBACK_SECRET).update(body).digest('hex');
  return `sha256=${expected}` === signature;
}

const server = createServer(async (req, res) => {
  if (req.url === '/callback/review_result' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      const signature = req.headers['x-callback-signature'] || '';
      if (!verifyHmac(body, signature)) {
        res.writeHead(403, { 'Content-Type': 'application/json' });
        res.end('{"error":"invalid signature"}');
        return;
      }
      const payload = JSON.parse(body);
      handleCallback(payload);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end('{"ok":true}');
    });
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

function handleCallback(payload) {
  // payload: { review_id, new_state, disposition, source_system, ... }
  // Find pipeline state file with matching review_id
  // If approved: spawn pipeline resume
  // If rejected: spawn git rollback
}
```

### Pattern 4: Telegram Photo Notification (Review Platform Side)
**What:** When review metadata contains preview_images, send them as Telegram photos before the InlineKeyboard message.
**When to use:** In `app/core/events.py` emit_state_change when new_state == "APPROVING" and source_system == "kais-movie-agent".
**Example:**
```python
# In emit_state_change, after fetching review:
metadata = review.metadata_json or {}
preview_images = metadata.get('preview_images', [])

# Send up to 3 photos before the text notification
if preview_images and source_system == 'kais-movie-agent':
    import base64
    from io import BytesIO
    for i, b64_data in enumerate(preview_images[:3]):
        try:
            image_bytes = base64.b64decode(b64_data)
            await _bot_app.bot.send_photo(
                chat_id=chat_id,
                photo=BytesIO(image_bytes),
                caption=f"Preview {i+1}" if len(preview_images) > 1 else None,
            )
        except Exception as e:
            logger.warning("telegram_photo_send_failed", error=str(e))

# Then send the text notification with InlineKeyboard as before
```

### Anti-Patterns to Avoid
- **Long-running pipeline process waiting for callback:** The pipeline MUST exit after submitting review. Using setTimeout/setInterval polling would hold resources and not survive process restarts. The callback-driven model is state-file + separate callback server.
- **Adding npm dependencies to movie-agent:** The movie-agent currently has zero npm dependencies (no package.json). Adding axios, express, or any package breaks this pattern. Use only Node.js built-in APIs.
- **Synchronous review in pipeline run loop:** The existing `run()` method iterates PHASES sequentially with `for...of`. After `_runRemoteReview()` returns `{ action: 'awaiting_review' }`, the loop must break and the process must exit, not continue to the next phase.
- **Deleting interactive-review.js:** The old review system should remain in the codebase (not deleted). Pipeline simply stops calling it. Other tools may still reference it.
- **Base64 images without size limits:** Telegram has a 10MB photo size limit. Images must be resized before base64 encoding. Without limits, a single 4K render could be 20MB+ in base64.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HMAC signature verification | Custom hash comparison | `crypto.createHmac('sha256', secret).update(body).digest('hex')` | Timing-safe comparison built in, standard Node.js API |
| JWT token caching | Manual expiry tracking | `Date.now() < this._tokenExpires` with 60s safety margin | Simple, proven pattern from gold-team client |
| HTTP timeout | Custom timer logic | `AbortSignal.timeout(ms)` in fetch options | Native Node.js API since v18, no external deps |
| Pipeline state persistence | Custom file locking | `writeFile` with atomic JSON serialization | Single writer (one pipeline at a time), no contention |
| Photo resizing | Custom image processing | Sharp or canvas in movie-agent, or enforce max dimensions at generation time | Image processing is complex; better to constrain at source |

**Key insight:** The movie-agent already has all the infrastructure needed (state persistence, resume, rollback). The integration adds a thin HTTP client layer and a callback server. Do not re-architect the pipeline.

## Common Pitfalls

### Pitfall 1: Pipeline Does Not Exit After Review Submission
**What goes wrong:** `_runRemoteReview()` returns a result, but `runPhase()` continues to `this.onPhaseComplete()` and the `run()` loop moves to the next phase.
**Why it happens:** The existing code treats review as a blocking step that always resolves with approve/reject. Remote review returns `awaiting_review` which is a new state the caller does not expect.
**How to avoid:** After `_runRemoteReview()` returns `{ action: 'awaiting_review' }`, `runPhase()` must throw a special error (e.g., `REVIEW_PENDING`) that the `run()` loop catches and breaks on. This is different from `REVIEW_REJECTED` which is a real failure.
**Warning signs:** Pipeline logs show "completed" for a phase that should be paused; next phase starts without approval.

### Pitfall 2: Callback Server Cannot Find Pipeline Workdir
**What goes wrong:** Callback server receives approval but cannot find which project directory has the matching review_id in its `.pipeline-state.json`.
**Why it happens:** The callback server runs on 192.168.71.38 which may host multiple project directories. The review_id alone does not identify which project.
**How to avoid:** Include the workdir path in the review metadata (e.g., `metadata.workdir`). The callback server reads metadata from the callback payload (which includes source_system metadata from the review record) to locate the correct `.pipeline-state.json` file. Alternatively, maintain a simple mapping file (`~/.review-mappings.json`) that maps review_id -> workdir.
**Warning signs:** Callback server logs "review_id not found in any pipeline state."

### Pitfall 3: Base64 Image Size Explosion
**What goes wrong:** A single scene render at 4K resolution is 8-15MB as PNG. Base64 encoding adds ~33% overhead. Three images in metadata would be 30-60MB, exceeding HTTP body limits and Telegram's 10MB photo limit.
**Why it happens:** No size constraints enforced on preview images before encoding.
**How to avoid:** (1) Resize images to max 1024px on longest side before base64 encoding in movie-agent. (2) Use JPEG compression (quality 0.8) instead of PNG for photo previews. (3) Cap total base64 payload at 5MB per review (3 images at ~1.7MB each max). (4) On the review platform side, validate metadata size in ReviewCreateRequest.
**Warning signs:** Review submission returns 413 (payload too large); Telegram sendPhoto fails with FILE_TOO_LARGE.

### Pitfall 4: Race Condition Between Callback and State File
**What goes wrong:** Callback arrives before pipeline state file is fully written (e.g., pipeline writes state file but has not yet exited when callback fires for AUTO-approved review).
**Why it happens:** AUTO-approved reviews complete synchronously: submit -> policy eval -> auto-approve -> callback delivery in <100ms. The pipeline may still be writing the state file.
**How to avoid:** (1) Pipeline must fully flush state file before considering submission complete. (2) Callback server should retry if it cannot find the review_id in state files (with short backoff: 1s, 3s). (3) For AUTO reviews, the callback server may need a small delay before processing.
**Warning signs:** Callback server logs "review_id X not found" for an AUTO-approved review that was just submitted.

### Pitfall 5: Callback URL Validation Blocks Movie-Agent
**What goes wrong:** Review platform validates callback URLs to RFC1918 addresses only (192.168.x.x, 10.x.x.x, 172.16-31.x.x). Movie-agent on 192.168.71.38 passes, but if someone configures a hostname that resolves differently, submission fails with 422.
**Why it happens:** The review platform's `validate_callback_url()` does DNS resolution before allowing the URL.
**How to avoid:** Always use IP address directly in callback_url: `http://192.168.71.38:8766/callback/review_result`. Document this requirement. The callback server port must be accessible from 192.168.71.140.
**Warning signs:** Review submission returns 422 with "Callback URL must resolve to a private IP address."

### Pitfall 6: Pipeline Resume Process Loses Context
**What goes wrong:** When callback server spawns `node pipeline.js resume character`, the new process does not have the original pipeline config (episode, workdir, hooks, callbacks).
**Why it happens:** `Pipeline.resume()` reads state from `.pipeline-state.json`, but the config (onPhaseComplete, onProgress callbacks) is not serialized.
**How to avoid:** Save sufficient config in the state file for resume to work. The existing resume() method already handles this -- it reads state and continues from the saved phase index. Ensure the spawned process passes the correct workdir argument.
**Warning signs:** Resume starts from wrong phase, or crashes due to missing config.

## Code Examples

### Review Platform Auth Token Exchange (Verified from Source)
```javascript
// Source: app/api/v1/auth.py (verified)
// POST /api/v1/auth/token
// Request: { api_key: string, client_id: string }
// Response: { data: { access_token: string, token_type: "bearer", expires_in: 900 } }

const resp = await fetch('http://192.168.71.140:8090/api/v1/auth/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ api_key: 'shared-secret-key', client_id: 'kais-movie-agent' }),
});
const { data } = await resp.json();
// data.access_token is a JWT valid for 900 seconds (15 minutes)
```

### Review Submission (Verified from Source)
```javascript
// Source: app/api/v1/reviews.py + app/models/schemas.py (verified)
// POST /api/v1/reviews
// Request body (ReviewCreateRequest):
//   type: string (1-50 chars)
//   content_ref: string (min 1)
//   source_system: string (min 1)
//   metadata: object | null
//   priority: "low" | "normal" | "high" | "critical"
//   risk_score: float (0.0-1.0) | null
//   callback_url: string | null
//   callback_secret: string | null
//
// Response (202 Accepted):
//   { data: { review_id: int, state: string, routing: "AUTO"|"HUMAN"|"AI_AUDIT"|"BLOCK" } }

const result = await client.submitReview({
  type: 'pipeline_phase',
  contentRef: 'EP01:art-direction',
  metadata: {
    phase_name: '美术方向',
    episode: 'EP01',
    preview_images: ['<base64-string-1>', '<base64-string-2>'],
  },
  callbackUrl: 'http://192.168.71.38:8766/callback/review_result',
  callbackSecret: 'hmac-shared-secret',
});
// result: { reviewId: 42, state: 'APPROVING', routing: 'HUMAN' }
```

### Callback Payload Format (Verified from Source)
```javascript
// Source: app/workers/tasks.py deliver_review_callback (verified)
// POST to callback_url with HMAC signature
// Headers: { 'X-Callback-Signature': 'sha256=<hex>' }
// Body (JSON):
//   {
//     review_id: int,
//     old_state: "APPROVING",
//     new_state: "COMPLETE",
//     timestamp: "2026-05-07T12:00:00+00:00",
//     source_system: "kais-movie-agent",
//     disposition: "HUMAN",           // from review record
//     disposition_action: "approve" | "reject"  // from callback_data format
//   }
```

### HMAC Verification (Node.js, mirrors Python implementation)
```javascript
// Source: Node.js crypto module, mirrors app/workers/tasks.py HMAC logic
import { createHmac } from 'node:crypto';

function verifyCallbackSignature(body, signatureHeader, secret) {
  if (!secret) return true; // Dev mode: no verification
  const expected = 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
  return expected === signatureHeader;
}
```

### GitStageManager Rollback (Verified from Source)
```javascript
// Source: lib/git-stage-manager.js (verified)
// rollback(targetStage) does git reset --hard to the stage's commit hash
// Returns { success: boolean, commitHash: string }

const git = new GitStageManager(workdir);
const result = await git.rollback('art-direction');
// result: { success: true, commitHash: 'abc12345' }
// After rollback, files are restored to checkpoint state
```

### Pipeline State File Format (Existing, Verified)
```json
// .pipeline-state.json (existing format, will be extended)
{
  "episode": "EP01",
  "phases": {
    "art-direction": {
      "status": "awaiting_review",
      "review_id": 42,
      "submitted_at": "2026-05-07T12:00:00.000Z"
    },
    "requirement": {
      "status": "completed",
      "completedAt": "2026-05-07T11:00:00.000Z",
      "result": {}
    }
  },
  "currentPhaseId": "art-direction",
  "startedAt": "2026-05-07T10:00:00.000Z"
}
```

### PHASES Array with Review Gates (Verified, 6 gates)
```javascript
// Source: lib/pipeline.js lines 12-38 (verified)
// Phases with review config (these get _runRemoteReview):
// 1. art-direction  (stageOrder 2) - art style selection
// 2. character       (stageOrder 3) - character design review
// 3. voice           (stageOrder 4.5) - voice audition
// 4. scene           (stageOrder 5) - scene image review
// 5. storyboard      (stageOrder 6) - storyboard review
// 6. camera          (stageOrder 7) - video clip review
//
// Phases WITHOUT review (skip review):
// - requirement (stageOrder 1) - review: false
// - scenario (stageOrder 4) - review: false
// - post-production (stageOrder 8) - review: false
// - quality-gate (stageOrder 8.5) - review: false
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Local browser review (interactive-review.js) | Remote review platform with Telegram approval | This phase | Pipeline becomes headless; reviews happen on mobile via Telegram |
| In-process blocking review | Callback-driven async review | This phase | Pipeline exits while waiting; callback server triggers resume |
| Single-node deployment | Two-machine architecture (71.38 + 71.140) | This phase | Network connectivity and callback URL validation become critical |

**Deprecated/outdated:**
- `Pipeline._runReview()`: Will be replaced by `_runRemoteReview()`. The old method and `interactive-review.js` remain in codebase but are no longer called by pipeline.

## Open Questions

1. **Review ID to Workdir Mapping**
   - What we know: Callback payload includes `review_id` and `source_system` but not the workdir path.
   - What's unclear: How callback-server.js discovers which workdir on 192.168.71.38 has the matching review_id in its state file.
   - Recommendation: Include `workdir` in review metadata at submission time. Callback server can read review metadata from the callback payload's enriched data, or maintain a lightweight mapping file. Claude's discretion per CONTEXT.md.

2. **Callback Server Lifecycle**
   - What we know: The callback server must be running to receive approval/rejection results. Movie-agent is on 192.168.71.38.
   - What's unclear: Whether the callback server should be a long-running daemon or started/stopped alongside the pipeline.
   - Recommendation: Long-running daemon (systemd or pm2) since multiple pipelines may submit reviews concurrently. Document as deployment requirement.

3. **Risk Score for Pipeline Phases**
   - What we know: Gold-team computes risk from task_type (GPU engine). Movie-agent phases are different.
   - What's unclear: What risk scores to assign to each pipeline phase.
   - Recommendation: Use moderate risk (0.5) for all phases by default. This matches the gold-team "unknown type" default and ensures HUMAN routing for initial deployment. Can be tuned per phase later.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | ReviewPlatformClient, callback-server | Yes (on 71.38) | 24.13.0 | -- |
| Review Platform API | Review submission + query | Yes (on 71.140) | Running at :8090 | -- |
| Network 71.38 <-> 71.140 | Callback delivery | Yes (verified ping) | LAN | -- |
| python-telegram-bot | Telegram sendPhoto | Yes | 22.7.0 | -- |
| Git | GitStageManager rollback | Yes (on 71.38) | system | -- |
| callback-server port (8766) | Callback receiver | Needs verification | -- | Configurable via env |

**Missing dependencies with no fallback:**
- None identified. All required tools are available.

**Missing dependencies with fallback:**
- None needed.

## Sources

### Primary (HIGH confidence)
- `/home/kai/workspace/kais-movie-agent/lib/pipeline.js` -- Pipeline class, _runReview(), runPhase(), resume(), PHASES array, state file format (read in full)
- `/home/kai/workspace/kais-movie-agent/lib/git-stage-manager.js` -- GitStageManager with checkpoint(), rollback(), stage registry (read in full)
- `/home/kai/workspace/kais-movie-agent/lib/interactive-review.js` -- Current review system being replaced (read in full)
- `/home/kai/workspace/kais-review-platform/app/api/v1/reviews.py` -- POST /api/v1/reviews endpoint, ReviewCreateRequest handling (read in full)
- `/home/kai/workspace/kais-review-platform/app/api/v1/auth.py` -- POST /api/v1/auth/token endpoint, API key to JWT exchange (read in full)
- `/home/kai/workspace/kais-review-platform/app/models/schemas.py` -- ReviewCreateRequest, ReviewResponse, ReviewSubmitResponse schemas (read in full)
- `/home/kai/workspace/kais-review-platform/app/integrations/gold_team/client.py` -- Python client pattern to mirror in Node.js (read in full)
- `/home/kai/workspace/kais-review-platform/app/workers/tasks.py` -- deliver_review_callback with HMAC signing, retry logic (read in full)
- `/home/kai/workspace/kais-review-platform/app/core/events.py` -- emit_state_change, Telegram notification trigger (read in full)
- `/home/kai/workspace/kais-review-platform/app/bot/notifications.py` -- build_notification_message, InlineKeyboard markup (read in full)
- `/home/kai/workspace/kais-review-platform/app/bot/handlers.py` -- callback_handler, approve/reject processing (read in full)
- `/home/kai/workspace/kais-review-platform/app/core/auth.py` -- JWT creation/validation, create_jwt() (read in full)
- `/home/kai/workspace/kais-review-platform/app/core/config.py` -- Settings with api_key, jwt_secret, telegram config (read in full)
- `/home/kai/workspace/kais-review-platform/app/core/validation.py` -- RFC1918 callback URL validation (read in full)
- Node.js v24.13.0 runtime verified: native fetch (typeof === 'function'), crypto.createHmac (typeof === 'function')

### Secondary (MEDIUM confidence)
- python-telegram-bot 22.7.0 `sendPhoto` API -- standard Bot API method, well-documented
- Telegram Bot API photo size limits -- 10MB per photo, well-documented constraint

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all APIs verified by reading source code, Node.js runtime tested on machine
- Architecture: HIGH -- both codebases fully read, integration points mapped precisely
- Pitfalls: HIGH -- identified from source code analysis of both systems, not theoretical

**Research date:** 2026-05-07
**Valid until:** 2026-06-07 (stable architecture, both codebases actively developed)
