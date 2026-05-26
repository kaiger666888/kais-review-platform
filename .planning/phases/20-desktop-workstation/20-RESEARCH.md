# Phase 20: Desktop Workstation - Research

**Researched:** 2026-05-17
**Domain:** Frontend (HTMX + Alpine.js + Tailwind v4 CDN) / Server-Side Rendering / Media Playback
**Confidence:** HIGH

## Summary

Phase 20 builds the 3-column desktop workstation UI for reviewers to efficiently review Shot Cards. The workstation is a server-rendered HTML page using the project's established HTMX + Alpine.js + Tailwind v4 CDN stack, with zero build steps. The left panel provides a filterable shot queue with cursor-based pagination and infinite scroll, the center panel offers media playback (HTML5 video, Canvas-based frame extraction, candidate grid), and the right panel presents narrative context, prompts, and decision buttons. Keyboard shortcuts are wired through Alpine.js `@keydown.document` listeners. Batch operations, dual-column comparison, and a policy drawer are togglable modes within the same page.

The core challenge is that this is a **frontend-heavy phase on a server-rendered stack**. The planner must balance server-side template rendering (HTMX partials for data) with client-side state management (Alpine.js for UI interactions like keyboard nav, batch selection, video playback). Media playback introduces a new dimension -- video source URLs from MinIO presigned URLs, client-side Canvas API for frame extraction, and the CORS implications of cross-origin video resources.

**Primary recommendation:** Build the workstation as a single Jinja2 page template (`workstation.html`) extending `base.html`, with Alpine.js managing all client-side state (active shot, selection, comparison mode, video playback) and HTMX handling data fetching (shot queue pagination, filter updates, decision POSTs). Create new server-side endpoints for media URLs and workstation-specific partials; reuse existing Shot Card API endpoints and SSE infrastructure for real-time updates.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- 3-column layout: Left 25% / Center 45% / Right 30% via Tailwind grid `grid-cols-[25fr_45fr_30fr]`
- Left panel shot queue uses cursor-based pagination via HTMX infinite scroll (`hx-get="/partials/shot-queue?cursor={last_id}"`)
- Server-side filtering via HTMX: filter controls send `hx-get` with query params (`?project=X&scene=Y&risk=HIGH`)
- Collapsible panels only -- click to collapse left/right panels to icon-only sidebar via Alpine.js `x-show` toggle. No drag-resize
- HTML5 `<video>` element -- native browser support, `currentTime` for scrubbing, styled with Tailwind
- Video source via MinIO presigned URLs -- `GET /api/v1/media/{shot_card_id}/video` generates presigned URL, template embeds as `<video src>`
- Frame extraction via Canvas API client-side -- `video.currentTime = frame_time`, draw to `<canvas>`, export as `toDataURL()`. First/last frame at `t=0` and `t=duration-0.1`
- Candidate thumbnail grid: Tailwind `grid-cols-3 gap-2` -- small thumbnails (80x45px, 16:9), click-to-switch via `hx-post`
- Alpine.js `@keydown.window` -- global listener in base template, maps keys to actions (Space=play/pause, Y/N=approve/reject, J/K=navigate, D=diff, B=batch, G=policy)
- Batch selection via Alpine.js array + CSS highlight -- `selectedItems: []`, Ctrl+click append, Shift+click range-select, `x-bind:class` for ring highlight. Batch action buttons appear when selection > 0
- Dual-column comparison: Overlay toggle in center panel -- Alpine.js `showComparison` toggles single view to side-by-side `grid-cols-2`. Mode selector: first-vs-last / current-vs-history / current-vs-reference
- Git policy view (G key): Slide-over panel from right -- Alpine.js drawer showing policy YAML + commit SHA, fetched via `hx-get="/api/v1/policies/{sha}"`

### Claude's Discretion
Implementation details for template structure, component decomposition, and test structure are at Claude's discretion.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-D-01 | 3-column workstation layout with shot queue (project/scene/risk filters), media preview (video player, frame viewer, candidate array), decision panel (narrative context, prompts, node status, decision buttons) | Tailwind CSS grid layout pattern, HTMX cursor-based pagination with infinite scroll, Alpine.js state management for active shot |
| UI-D-02 | Keyboard shortcuts -- Space play/pause, Y/N approve/reject, J/K navigate shots, D diff compare, B batch, G git policy, L log | Alpine.js `@keydown.document` with `.prevent` modifier, key-to-action mapping in `x-data` component |
| UI-D-03 | Dual-column comparison -- first frame vs last frame, current candidate vs history, current vs reference | Alpine.js toggle state, HTML5 Canvas API frame extraction, side-by-side grid layout |
| UI-D-04 | Batch operations -- Ctrl/Shift multi-select left panel shots, one-click batch approve/reject/suspend | Alpine.js `selectedItems` array, Shift+click range select via index tracking, existing batch API endpoints at `/api/v1/reviews/batch/approve` and `/batch/reject` |
| UI-D-05 | Candidate array -- same shot multiple pull-card result thumbnail array, click to seamlessly switch | Tailwind `grid-cols-3` grid, Alpine.js `selectedCandidate` state, candidate data from `visual_bundle.candidates` JSONB field |
| MEDIA-01 | Video playback infrastructure -- video stream endpoint, frame extraction, timeline control | MinIO presigned URL endpoint, HTML5 `<video>` element, Canvas API `drawImage` + `seeked` event pattern |
| MEDIA-02 | Thumbnail generation -- first frame / last frame / candidate thumbnail auto-generation | Client-side Canvas API frame extraction on video load, `toDataURL()` export, async `seeked` event handling |
| MEDIA-03 | Candidate comparison view -- multi-pull-card candidates side-by-side / overlay comparison | Dual-column comparison mode reusing MEDIA-01 infrastructure, overlay with opacity slider or side-by-side grid |
</phase_requirements>

## Standard Stack

### Core (Frontend - Already in Project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| HTMX | 2.0.9 | Server-rendered HTML fragments | Project standard for all dynamic content loading, SSE integration, form submissions |
| HTMX SSE Extension | 2.2.4 | SSE support in HTMX v2 | Required for real-time shot card updates via EventSource |
| Alpine.js | 3.15.12 | Client-side state management | Project standard for keyboard shortcuts, UI toggles, local state |
| Tailwind CSS (Browser) | 4.x (`@tailwindcss/browser`) | Utility-first CSS | Project standard via CDN, zero-build, v4 engine rewrite |
| Jinja2 | 3.1.6 | Server-side templates | FastAPI built-in, used for all page and partial rendering |
| jinja2-fragments | 1.8.0 | Partial template rendering | Configured in project for HTMX block rendering |

### Core (Backend - Already in Project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136.1 | Web framework | Async route handlers, Jinja2 template rendering, SSE |
| SQLAlchemy | 2.0.49 | ORM + query builder | Shot Card queries, cursor-based pagination, filtering |
| redis-py | 5.3.1 | Redis client (async) | SSE connection registry, state machine store |

### Supporting (May Need Addition)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| minio | 7.2.20 | MinIO Python client | Already in requirements.txt for presigned URL generation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Alpine.js keyboard shortcuts | Mousetrap.js | Mousetrap is more featured but adds a dependency; Alpine.js `@keydown.document` handles this natively and is already loaded |
| Client-side Canvas frame extraction | Server-side FFmpeg frame extraction | Server-side is more reliable but adds FFmpeg binary dependency (violates Docker constraints); Canvas API works for basic first/last frame |
| Tailwind v4 CDN | Tailwind CLI build | CLI build is more performant but requires Node.js build step (violates zero-build constraint) |

**Installation:**
No new npm/pip packages needed. All frontend libraries loaded via CDN (already configured in `base.html`). All backend packages already in `requirements.txt`.

## Architecture Patterns

### Recommended Project Structure
```
app/
├── templates/
│   ├── base.html                          # Master layout (exists)
│   ├── pages/
│   │   ├── workstation.html               # NEW: Desktop workstation page
│   │   ├── dashboard.html                 # Existing V1 dashboard
│   │   └── login.html                     # Existing login
│   └── partials/
│       ├── _shot_queue_card.html          # NEW: Single shot card in queue
│       ├── _shot_queue_list.html          # NEW: Shot queue list container
│       ├── _media_player.html             # NEW: Video player + candidate grid
│       ├── _decision_panel.html           # NEW: Context + prompts + buttons
│       ├── _comparison_view.html          # NEW: Side-by-side comparison
│       ├── _batch_toolbar.html            # NEW: Batch mode action bar
│       ├── _policy_drawer.html            # NEW: Git policy slide-over
│       ├── _reject_confirm.html           # Exists (reuse pattern)
│       └── _toast.html                    # Exists (reuse)
├── web/
│   ├── routes.py                          # EXTEND: Add workstation routes
│   ├── sse.py                             # Exists (reuse for real-time)
│   └── auth.py                            # Exists (reuse for cookie auth)
└── api/
    └── v1/
        ├── shot_cards.py                  # Exists (reuse for data queries)
        ├── media.py                       # NEW: Media URL endpoints
        └── actions.py                     # Exists (reuse for approve/reject)
```

### Pattern 1: HTMX Infinite Scroll for Shot Queue
**What:** Load shot cards progressively as the user scrolls down the left panel.
**When to use:** Left panel shot queue pagination.
**Example:**
```html
<!-- Last card in the current batch acts as scroll sentinel -->
<div class="shot-card"
     hx-get="/partials/shot-queue?cursor={{ last_shot_id }}&project={{ project_filter }}"
     hx-trigger="intersect once"
     hx-swap="afterend"
     hx-target="this">
  <!-- card content -->
</div>
```
**Source:** [HTMX Infinite Scroll Example](https://htmx.org/examples/infinite-scroll/)

**Important note:** Use `intersect once` instead of `revealed` when the scroll container uses `overflow-y: scroll` (which the left panel will). The `revealed` trigger only works with document-level scrolling.

### Pattern 2: Alpine.js Global Keyboard Shortcuts
**What:** Global keyboard event listener mapped to workstation actions.
**When to use:** All keyboard shortcuts (Space, Y/N, J/K, D, B, G, L, Esc).
**Example:**
```html
<!-- On the workstation root element, NOT @keydown.window -->
<div x-data="workstationState()"
     @keydown.document.prevent.space="togglePlay()"
     @keydown.document.prevent.y="approve()"
     @keydown.document.prevent.n="reject()"
     @keydown.document.prevent.j="nextShot()"
     @keydown.document.prevent.k="prevShot()"
     @keydown.document.prevent.d="toggleComparison()"
     @keydown.document.prevent.b="toggleBatchMode()"
     @keydown.document.prevent.g="togglePolicy()"
     @keydown.document.prevent.l="toggleLog()"
     @keydown.document.prevent.escape="resetMode()">
  <!-- 3-column layout -->
</div>
```

**Critical:** Use `@keydown.document.prevent` NOT `@keydown.window.prevent`. Per [GitHub Discussion #3277](https://github.com/alpinejs/alpine/discussions/3277), `.prevent` does not work reliably with `.window` scope in Alpine.js. The `.document` scope works correctly with `.prevent` for `preventDefault()`. Use `@keydown` (not `@keyup`) for best results with `preventDefault()`.

**Guard against input conflicts:** Keyboard shortcuts must NOT fire when the user is typing in a text field (e.g., reject reason textarea). Add a check in each handler:
```javascript
function handleKey(e) {
    const tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    // ... handle shortcut
}
```
Or use Alpine.js event modifiers to exclude inputs.

### Pattern 3: Server-Side Filtering via HTMX
**What:** Filter controls trigger HTMX GET requests that re-render the shot queue partial.
**When to use:** Project/scene/risk filter dropdowns in the left panel header.
**Example:**
```html
<select name="project"
        hx-get="/partials/shot-queue"
        hx-target="#shot-queue-list"
        hx-swap="innerHTML"
        hx-include="[name='scene'],[name='risk']">
  <option value="">All Projects</option>
  {% for p in projects %}
  <option value="{{ p }}">{{ p }}</option>
  {% endfor %}
</select>
```
This sends `GET /partials/shot-queue?project=X&scene=Y&risk=HIGH` and swaps the returned HTML into the queue container.

### Pattern 4: Media URL Generation (MinIO Presigned URLs)
**What:** Server-side endpoint generates short-lived MinIO presigned URLs for video/image access.
**When to use:** Video playback and thumbnail display.
**Example:**
```python
# New endpoint: GET /api/v1/media/{shot_card_id}/video
from minio import MinIO
from datetime import timedelta

@router.get("/api/v1/media/{shot_card_id}/video")
async def get_media_url(shot_card_id: int, db: AsyncSession = Depends(get_db)):
    shot_card = await db.get(ShotCard, shot_card_id)
    if not shot_card or not shot_card.visual_bundle:
        raise HTTPException(404)
    video_url = shot_card.visual_bundle.get("video_clip", {}).get("url")
    # Generate presigned URL from MinIO
    presigned = minio_client.presigned_get_object(
        bucket_name="review-platform",
        object_name=video_url,
        expires=timedelta(minutes=15)
    )
    return {"url": presigned}
```

### Pattern 5: Client-Side Frame Extraction (Canvas API)
**What:** Extract video frames client-side using HTML5 Canvas API.
**When to use:** First frame, last frame, and candidate thumbnail generation.
**Example:**
```javascript
function captureFrame(videoEl, timeInSeconds) {
    return new Promise((resolve) => {
        videoEl.currentTime = timeInSeconds;
        videoEl.addEventListener('seeked', () => {
            const canvas = document.createElement('canvas');
            canvas.width = videoEl.videoWidth;
            canvas.height = videoEl.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
            resolve(canvas.toDataURL('image/jpeg', 0.7));
        }, { once: true });
    });
}

// Usage: extract first and last frames when video loads
videoEl.addEventListener('loadedmetadata', async () => {
    const first = await captureFrame(videoEl, 0);
    const last = await captureFrame(videoEl, Math.max(0, videoEl.duration - 0.1));
});
```

### Pattern 6: SSE Real-time Shot Queue Updates
**What:** HTMX SSE extension listens for shot card events and updates the queue.
**When to use:** New shot cards arrive, status changes on existing cards.
**Example:**
```html
<div hx-ext="sse" sse-connect="/events/stream">
  <div id="shot-queue-list"
       sse-swap="shot_card_created,shot_card_updated"
       hx-get="/partials/shot-queue"
       hx-trigger="sse:shot_card_updated, load"
       hx-target="#shot-queue-list"
       hx-swap="innerHTML">
  </div>
</div>
```

### Pattern 7: Batch Selection with Shift+Click Range
**What:** Multi-select shots in the queue using Ctrl+Click (append) and Shift+Click (range).
**When to use:** Batch approve/reject operations.
**Example:**
```javascript
// In Alpine.js x-data
{
    selectedItems: [],
    lastClickedIndex: null,
    allShots: [], // populated from server

    toggleSelect(shotId, index, event) {
        if (event.shiftKey && this.lastClickedIndex !== null) {
            // Range select
            const start = Math.min(this.lastClickedIndex, index);
            const end = Math.max(this.lastClickedIndex, index);
            for (let i = start; i <= end; i++) {
                if (!this.selectedItems.includes(this.allShots[i].id)) {
                    this.selectedItems.push(this.allShots[i].id);
                }
            }
        } else if (event.ctrlKey || event.metaKey) {
            // Toggle individual
            const idx = this.selectedItems.indexOf(shotId);
            if (idx > -1) this.selectedItems.splice(idx, 1);
            else this.selectedItems.push(shotId);
        } else {
            // Single select (replace)
            this.selectedItems = [shotId];
        }
        this.lastClickedIndex = index;
    }
}
```

### Anti-Patterns to Avoid
- **SPA thinking with HTMX:** Do NOT try to manage shot data state client-side in Alpine.js and then render it. Use HTMX for data fetching and DOM updates; use Alpine.js only for UI state (active, selected, mode toggles).
- **Polling instead of SSE:** Do NOT use `setInterval` + HTMX polling for real-time updates. The SSE infrastructure already exists and is more efficient.
- **Server-side frame extraction:** Do NOT add FFmpeg to the Docker image for thumbnail generation. The Canvas API handles first/last frame extraction client-side without any server dependency.
- **Custom CSS for layout:** Do NOT write custom CSS for the 3-column grid. Use Tailwind's grid utilities (`grid grid-cols-[25fr_45fr_30fr]`) as specified in the locked decisions.
- **Separate page for each mode:** Comparison, batch, and policy views are modes WITHIN the workstation page, not separate routes. They toggle via Alpine.js state.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Infinite scroll pagination | Custom IntersectionObserver + fetch | HTMX `hx-trigger="intersect once"` | HTMX handles DOM swap, loading indicators, and error states natively |
| Real-time updates | Polling with setInterval | HTMX SSE extension (`sse-swap`) | SSE infrastructure already exists in `app/web/sse.py` |
| Keyboard shortcut system | Custom addEventListener dispatcher | Alpine.js `@keydown.document` | Alpine.js manages listener lifecycle, event cleanup, and state integration |
| Video playback controls | Custom video UI framework | HTML5 `<video>` element + native controls | Native `<video>` supports play/pause, seeking, volume, fullscreen with zero code |
| Thumbnail generation | Server-side FFmpeg pipeline | Client-side Canvas API | No server dependency, works for basic frame extraction, handles CORS with presigned URLs |
| Batch API calls | Individual sequential POSTs | Existing `/api/v1/reviews/batch/approve` and `/batch/reject` endpoints | Already implemented in Phase 18 with 207 Multi-Status responses |
| Dark theme styling | Custom CSS color variables | Tailwind dark mode utilities (`bg-gray-900`, `text-gray-200`) | Tailwind v4 provides all needed dark palette utilities |

**Key insight:** This phase is primarily about composing existing infrastructure (HTMX, Alpine.js, Tailwind, SSE, Shot Card API, batch endpoints) into a workstation UI. The only truly new backend code is the media URL presigned endpoint. Everything else is template rendering and client-side state management.

## Common Pitfalls

### Pitfall 1: Canvas API CORS Taint on Cross-Origin Video
**What goes wrong:** `canvas.toDataURL()` throws `SecurityError` when the video source is cross-origin (MinIO on a different host/port).
**Why it happens:** MinIO runs on a different port or host from the FastAPI app. The canvas becomes "tainted" when a cross-origin resource is drawn onto it.
**How to avoid:** (1) Set `crossOrigin="anonymous"` on the `<video>` element. (2) Configure MinIO/CORS to allow the origin. (3) Alternatively, serve video through FastAPI as a reverse proxy (avoids CORS entirely but adds bandwidth load). (4) Presigned URLs with proper CORS headers on MinIO bucket.
**Warning signs:** Blank thumbnails, console errors about "tainted canvas" or "SecurityError".

### Pitfall 2: Keyboard Shortcuts Firing in Text Inputs
**What goes wrong:** Pressing 'Y' while typing a reject reason triggers approve action.
**Why it happens:** Global `@keydown.document` captures all key events including those in text fields.
**How to avoid:** Add an input guard in every keyboard handler that checks `event.target.tagName` and skips if it's INPUT, TEXTAREA, or SELECT. Alpine.js custom event handlers can include this guard.
**Warning signs:** Unexpected navigation or actions while typing in filter inputs or reject reason textarea.

### Pitfall 3: Alpine.js `.prevent` Not Working with `.window` Scope
**What goes wrong:** Keyboard shortcuts fire but browser defaults also trigger (e.g., Space scrolls the page).
**Why it happens:** Alpine.js `.prevent` modifier does not work reliably with `.window` scope per [GitHub Discussion #3277](https://github.com/alpinejs/alpine/discussions/3277).
**How to avoid:** Use `@keydown.document.prevent` instead of `@keydown.window.prevent`.
**Warning signs:** Browser default actions (scrolling, quick-find) still occur alongside keyboard shortcuts.

### Pitfall 4: HTMX Infinite Scroll with `overflow-y: scroll` Container
**What goes wrong:** `revealed` trigger never fires because the scroll container is not the document body.
**Why it happens:** `revealed` uses IntersectionObserver on the document viewport, not nested scrollable containers.
**How to avoid:** Use `hx-trigger="intersect once"` instead of `hx-trigger="revealed"` for elements inside `overflow-y: scroll` containers.
**Warning signs:** "Load more" sentinel element appears but never triggers loading.

### Pitfall 5: Video `currentTime = duration` Returns Blank Last Frame
**What goes wrong:** Setting `currentTime` to exactly `video.duration` seeks past the last frame, resulting in a blank/black capture.
**Why it happens:** The duration is the end timestamp, not the timestamp of the last visible frame.
**How to avoid:** Use `currentTime = Math.max(0, duration - 0.1)` to seek to 100ms before the end.
**Warning signs:** Last frame thumbnail is consistently black or blank.

### Pitfall 6: SSE Event Name Mismatch
**What goes wrong:** SSE events arrive but HTMX does not swap content.
**Why it happens:** The event name in `sse-swap` or `hx-trigger="sse:..."` must exactly match the event name sent by the server. The existing SSE endpoint sends `review_status` as the event name; Shot Card events will need a different event name.
**How to avoid:** Verify SSE event names match between `EventSourceResponse` server-side and `sse-swap`/`hx-trigger` client-side. The workstation will need to listen for new event types like `shot_card_updated`.
**Warning signs:** Network tab shows SSE messages arriving but DOM does not update.

### Pitfall 7: Shift+Click Range Select Off-by-One
**What goes wrong:** Range selection includes one extra or one fewer item than expected.
**Why it happens:** The range calculation needs to be inclusive on both ends, and the "last clicked" index must track the most recent non-shift click.
**How to avoid:** Use `Math.min/max` for inclusive range, track `lastClickedIndex` only on non-shift clicks, and reset on batch mode exit.
**Warning signs:** User selects shots 3-7 but gets shots 3-6 or 3-8.

### Pitfall 8: Presigned URL Expiration During Long Review Sessions
**What goes wrong:** Video stops loading after 15 minutes because the MinIO presigned URL expired.
**Why it happens:** Reviewers may spend extended time on a single shot card.
**How to avoid:** Set presigned URL expiration to a reasonable window (e.g., 1 hour) and re-generate on demand. Alternatively, add a refresh mechanism that re-requests the media URL when playback fails.
**Warning signs:** "403 Forbidden" errors on video resources after extended idle time.

## Code Examples

### Workstation Page Template Structure
```html
<!-- app/templates/pages/workstation.html -->
{% extends "base.html" %}

{% block title %}Desktop Workstation - Kai's Review Platform{% endblock %}

{% block content %}
<div x-data="workstationState()"
     @keydown.document.prevent.space="togglePlay()"
     @keydown.document.prevent.y="approve()"
     @keydown.document.prevent.n="reject()"
     @keydown.document.prevent.j="nextShot()"
     @keydown.document.prevent.k="prevShot()"
     @keydown.document.prevent.d="toggleComparison()"
     @keydown.document.prevent.b="toggleBatchMode()"
     @keydown.document.prevent.g="togglePolicy()"
     @keydown.document.prevent.escape="resetMode()"
     class="h-screen flex flex-col bg-gray-900">

  <!-- Top toolbar -->
  <header class="h-12 bg-gray-800 border-b border-gray-700 flex items-center px-4">
    <h1 class="text-gray-200 text-sm font-semibold">Desktop Workstation</h1>
    <!-- Batch toolbar (visible when batch mode active) -->
    <template x-if="selectedItems.length > 0">
      <div class="ml-auto flex items-center gap-2">
        <span class="text-yellow-400 text-xs" x-text="selectedItems.length + ' selected'"></span>
        <button @click="batchApprove()" class="px-3 py-1 bg-green-600 text-white text-xs rounded">Approve</button>
        <button @click="batchReject()" class="px-3 py-1 bg-red-600 text-white text-xs rounded">Reject</button>
      </div>
    </template>
  </header>

  <!-- 3-column grid -->
  <div class="flex-1 grid grid-cols-[25fr_45fr_30fr] overflow-hidden">

    <!-- LEFT: Shot Queue -->
    <div class="border-r border-gray-700 flex flex-col overflow-hidden"
         x-show="!leftCollapsed">
      <!-- Filter controls (HTMX) -->
      {% include "partials/_shot_queue_filters.html" %}
      <!-- Shot list (HTMX infinite scroll) -->
      <div id="shot-queue-list" class="flex-1 overflow-y-auto"
           hx-ext="sse" sse-connect="/events/stream"
           hx-get="/partials/shot-queue" hx-trigger="load, sse:shot_card_updated"
           hx-target="#shot-queue-list" hx-swap="innerHTML">
      </div>
    </div>

    <!-- CENTER: Media Preview -->
    <div class="flex flex-col overflow-hidden p-4">
      {% include "partials/_media_player.html" %}
    </div>

    <!-- RIGHT: Decision Panel -->
    <div class="border-l border-gray-700 flex flex-col overflow-y-auto p-4"
         x-show="!rightCollapsed">
      {% include "partials/_decision_panel.html" %}
    </div>

  </div>

  <!-- Policy drawer (slide-over from right) -->
  <div x-show="showPolicy" x-transition class="fixed inset-y-0 right-0 w-96 bg-gray-800 border-l border-gray-700 shadow-xl z-50 overflow-y-auto p-6">
    <div id="policy-content"
         hx-get="/api/v1/policies/current" hx-trigger="showPolicy from:window"
         hx-swap="innerHTML">
    </div>
  </div>
</div>

<script>
function workstationState() {
  return {
    activeShotId: null,
    activeShot: null,
    selectedItems: [],
    lastClickedIndex: null,
    showComparison: false,
    showPolicy: false,
    batchMode: false,
    leftCollapsed: false,
    rightCollapsed: false,
    allShots: [],

    // ... methods
    nextShot() { /* navigate to next shot in allShots */ },
    prevShot() { /* navigate to prev shot in allShots */ },
    approve() { /* POST approve for activeShot */ },
    reject() { /* show reject dialog */ },
    togglePlay() { /* video.play()/pause() */ },
    toggleComparison() { this.showComparison = !this.showComparison; },
    toggleBatchMode() { this.batchMode = !this.batchMode; if (!this.batchMode) this.selectedItems = []; },
    togglePolicy() { this.showPolicy = !this.showPolicy; },
    resetMode() { this.showComparison = false; this.showPolicy = false; this.batchMode = false; this.selectedItems = []; },
  };
}
</script>
{% endblock %}
```

### Shot Queue Partial Template
```html
<!-- app/templates/partials/_shot_queue_list.html -->
{% for shot in shots %}
<div class="p-2 hover:bg-gray-750 cursor-pointer flex items-center gap-2"
     x-bind:class="{
       'ring-2 ring-blue-500 bg-gray-750': activeShotId === {{ shot.id }},
       'ring-2 ring-yellow-500': selectedItems.includes({{ shot.id }})
     }"
     @click="selectShot({{ shot.id }}, {{ loop.index0 }}, $event)"
     x-init="$watch('activeShotId', val => { if (val === {{ shot.id }}) $el.scrollIntoView({block:'nearest'}) })">

  {% if shot.visual_bundle and shot.visual_bundle.keyframes and shot.visual_bundle.keyframes.first %}
  <img class="w-16 h-9 object-cover rounded"
       src="{{ shot.visual_bundle.keyframes.first.url }}"
       alt="Shot {{ shot.narrative_context.shot_number }}" />
  {% else %}
  <div class="w-16 h-9 bg-gray-700 rounded flex items-center justify-center">
    <span class="text-gray-500 text-xs">--</span>
  </div>
  {% endif %}

  <div class="flex-1 min-w-0">
    <div class="text-sm text-gray-200 truncate">
      Shot {{ shot.narrative_context.shot_number }}
    </div>
    <div class="text-xs text-gray-400">
      Scene {{ shot.narrative_context.scene }}
    </div>
  </div>

  <span class="text-xs px-1.5 py-0.5 rounded
    {% if shot.routing_decision == 'HUMAN' %}bg-red-900 text-red-300
    {% elif shot.routing_decision == 'AI_AUDIT' %}bg-yellow-900 text-yellow-300
    {% else %}bg-green-900 text-green-300{% endif %}">
    {{ shot.audit_status }}
  </span>
</div>
{% endfor %}

{% if has_more %}
<div hx-get="/partials/shot-queue?cursor={{ next_cursor }}"
     hx-trigger="intersect once"
     hx-swap="afterend"
     hx-target="this"
     class="p-4 text-center text-gray-500 text-xs">
  Loading more...
</div>
{% endif %}
```

### Media Player with Canvas Frame Extraction
```html
<!-- app/templates/partials/_media_player.html -->
<div class="flex-1 flex flex-col gap-3">
  <!-- Video player -->
  <div class="relative bg-black rounded-lg overflow-hidden aspect-video">
    <video id="shot-video" class="w-full h-full"
           x-effect="if (activeShot) loadVideo(activeShot)"
           preload="metadata" crossorigin="anonymous">
    </video>
    <!-- Play/Pause overlay -->
    <div class="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 hover:opacity-100 transition-opacity cursor-pointer"
         @click="togglePlay()">
      <svg x-show="!isPlaying" class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 24 24">
        <path d="M8 5v14l11-7z"/>
      </svg>
    </div>
  </div>

  <!-- Candidate grid -->
  <div class="grid grid-cols-3 gap-2">
    <template x-for="(cand, idx) in activeShot?.visual_bundle?.candidates || []" :key="idx">
      <button class="relative rounded overflow-hidden border-2"
              :class="selectedCandidate === idx ? 'border-blue-500' : 'border-transparent'"
              @click="selectedCandidate = idx; loadCandidate(idx)">
        <img class="w-full h-12 object-cover" :src="cand.keyframes?.first?.url || ''" />
        <span class="absolute bottom-0 right-0 text-xs bg-black/60 px-1" x-text="idx + 1"></span>
      </button>
    </template>
  </div>

  <!-- Frame comparison toggle -->
  <div class="flex items-center gap-2 text-xs text-gray-400">
    <button @click="showComparison = !showComparison"
            :class="showComparison ? 'text-blue-400' : 'text-gray-500'"
            class="px-2 py-1 rounded bg-gray-800 hover:bg-gray-700">
      [D] Comparison
    </button>
    <template x-if="showComparison">
      <div class="grid grid-cols-2 gap-2">
        <img :src="firstFrame" class="rounded border border-gray-700" alt="First frame" />
        <img :src="lastFrame" class="rounded border border-gray-700" alt="Last frame" />
      </div>
    </template>
  </div>
</div>
```

### New Route: Workstation Page
```python
# In app/web/routes.py (extend existing router)

@router.get("/workstation", response_class=HTMLResponse)
async def workstation(request: Request):
    """Desktop workstation for efficient Shot Card review."""
    try:
        user = await get_template_user(
            access_token=request.cookies.get("access_token"),
        )
    except Exception:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(request, "pages/workstation.html", {
        "user": user,
    })


@router.get("/partials/shot-queue", response_class=HTMLResponse)
async def shot_queue_partial(
    request: Request,
    project: str | None = None,
    scene: str | None = None,
    risk: str | None = None,
    cursor: int | None = None,
):
    """HTMX partial: Shot card queue with filters and cursor pagination."""
    PAGE_SIZE = 30
    async with async_session_factory() as session:
        query = select(ShotCard).order_by(ShotCard.id.asc()).limit(PAGE_SIZE + 1)
        if cursor:
            query = query.where(ShotCard.id > cursor)
        if project:
            query = query.where(ShotCard.project_id == project)
        if risk:
            query = query.where(ShotCard.routing_decision == risk)
        # Scene filter requires JSONB query
        if scene:
            query = query.where(
                ShotCard.narrative_context["scene"].astext == scene
            )

        result = await session.execute(query)
        shots = list(result.scalars().all())
        has_more = len(shots) > PAGE_SIZE
        shots = shots[:PAGE_SIZE]
        next_cursor = shots[-1].id if has_more and shots else None

    return templates.TemplateResponse(request, "partials/_shot_queue_list.html", {
        "shots": shots,
        "has_more": has_more,
        "next_cursor": next_cursor,
    })
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HTMX v1 `hx-sse` attribute | HTMX v2 SSE extension (`ext="sse"`, `sse-connect`, `sse-swap`) | HTMX 2.0 (2023) | Project already uses v2 pattern with `hx-ext="sse"` |
| Tailwind CDN `cdn.tailwindcss.com` | Tailwind v4 `@tailwindcss/browser` | Tailwind v4 (2025) | Project already uses v4 browser package via `unpkg.com/@tailwindcss/browser@4` |
| Alpine.js `.window` scope for keyboard | Alpine.js `.document` scope with `.prevent` | Alpine.js 3.x | `.document` works reliably with `.prevent`; `.window` does not |
| Server-side video thumbnail generation | Client-side Canvas API + `toDataURL()` | HTML5 mature | Avoids FFmpeg dependency, works for basic frame extraction |

**Deprecated/outdated:**
- `hx-sse="connect:..."` (HTMX v1 syntax): Replaced by `sse-connect="..."` in the HTMX v2 SSE extension
- `cdn.tailwindcss.com` (Tailwind v3 Play CDN): Replaced by `@tailwindcss/browser@4` for v4

## Open Questions

1. **MinIO CORS Configuration for Canvas Frame Extraction**
   - What we know: MinIO is configured in `config.py` with `minio_endpoint: str = "minio:9000"`. The Canvas API requires `crossOrigin="anonymous"` on `<video>` and proper CORS headers from MinIO.
   - What's unclear: Whether MinIO CORS is already configured to allow the FastAPI origin. If not, presigned URL approach may still fail for Canvas operations.
   - Recommendation: Plan for both (1) MinIO CORS configuration and (2) a fallback where frame extraction uses keyframe URLs from `visual_bundle.keyframes` (which are pre-generated image URLs) instead of Canvas extraction from video. The `visual_bundle.keyframes.first.url` and `visual_bundle.keyframes.last.url` fields already store keyframe image URLs.

2. **SSE Event Types for Shot Cards**
   - What we know: The existing SSE endpoint broadcasts `review_status` events. Shot Card aggregation emits `shot_card_updated` and `shot_card_created` events (defined in `app/core/event_types.py`).
   - What's unclear: Whether the existing SSE endpoint at `/events/stream` already broadcasts Shot Card events, or if it only broadcasts Review events.
   - Recommendation: The planner should verify and potentially extend `emit_state_change()` or create a parallel broadcast for Shot Card events. The workstation SSE listener needs to subscribe to shot card-specific events.

3. **Data Model: Shot Card vs Review for Workstation**
   - What we know: The project has TWO data models: `Review` (V1, in `app/models/schema.py`) and `ShotCard` (V2, in `app/models/shot_card.py`). The workstation should use ShotCard as the primary model.
   - What's unclear: Whether approve/reject actions should use the V1 state machine (`transition_state` on Review) or need a new Shot Card-specific state machine.
   - Recommendation: The CONTEXT.md says "decision actions (approve/reject) POST to existing or new endpoints". Given Phase 18 already built batch endpoints for Reviews, the planner should determine whether Shot Cards have their own approval flow or reuse the Review flow. Based on the ShotCard model having its own `audit_status` field (`awaiting_audit`, `approved`, `rejected`), it likely needs its own approval endpoints.

## Environment Availability

> This phase has minimal external dependencies. The workstation is a server-rendered HTML page using CDN-loaded frontend libraries.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MinIO | Media presigned URLs | Needs verification | 7.2.20 (client lib) | Use keyframe URLs directly from `visual_bundle.keyframes` (no presigned URL needed) |
| Redis | SSE connections | In Docker Compose | 7.x (alpine) | -- |
| PostgreSQL | Shot Card queries | Phase 15 dependency | TimescaleDB | -- |
| Browser (Chrome/Firefox) | Canvas API, HTML5 Video | User machine | Modern (2024+) | -- |

**Missing dependencies with no fallback:**
- None identified. All core dependencies are project-standard.

**Missing dependencies with fallback:**
- MinIO presigned URLs: If MinIO is not yet deployed (Phase 22 scope), fall back to using `visual_bundle.keyframes.*.url` directly as `<img>` sources. Frame comparison can use these pre-generated keyframes instead of Canvas extraction.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `app/templates/base.html`, `app/web/routes.py`, `app/web/sse.py`, `app/core/events.py`, `app/models/shot_card.py`, `app/models/schemas.py`, `app/api/v1/shot_cards.py`, `app/api/v1/actions.py`
- HTMX Infinite Scroll pattern: [htmx.org/examples/infinite-scroll](https://htmx.org/examples/infinite-scroll/)
- HTMX SSE Extension v2 docs: [htmx.org/extensions/sse](https://htmx.org/extensions/sse/)
- Alpine.js `.prevent` with `.document` scope: [GitHub Discussion #3277](https://github.com/alpinejs/alpine/discussions/3277)
- Alpine.js `x-on` directive: [alpinejs.dev/directives/on](https://alpinejs.dev/directives/on)
- MDN `HTMLCanvasElement.toDataURL()`: [developer.mozilla.org](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toDataURL)

### Secondary (MEDIUM confidence)
- HTML5 Video frame extraction pattern: Multiple community sources (Stack Overflow, Medium, Dave Rupert blog) confirm the `currentTime` + `seeked` + `drawImage` + `toDataURL` pattern
- Tailwind CSS v4 Play CDN: [tailwindcss.com/docs/installation/play-cdn](https://tailwindcss.com/docs/installation/play-cdn)
- Tailwind CSS v4 dark mode: [tailwindcss.com/docs/dark-mode](https://tailwindcss.com/docs/dark-mode)

### Tertiary (LOW confidence)
- MinIO presigned URL CORS behavior: Not directly verified; assumption that CORS headers on presigned URLs allow Canvas access. Flagged for validation during implementation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in the project, verified in requirements.txt and base.html
- Architecture: HIGH -- patterns follow existing codebase conventions (HTMX partials, Alpine.js state, Tailwind utilities)
- Pitfalls: HIGH -- Alpine.js `.document` vs `.window` issue verified via GitHub discussion; Canvas CORS issue well-documented; HTMX `intersect` vs `revealed` verified in official docs
- Media playback: MEDIUM -- Canvas frame extraction pattern is well-established but CORS interaction with MinIO presigned URLs needs runtime verification

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (stable stack, low churn expected)
