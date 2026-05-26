---
phase: 25-analytics-dashboard
plan: 01
subsystem: analytics
tags: [analytics, dashboard, batch-review, metrics, routing-ratio, score-distribution]
dependency_graph:
  requires: [app/models/schema.py, app/models/shot_card.py, app/core/state_machine.py]
  provides: [analytics-api, analytics-dashboard-page, batch-review-ui]
  affects: [app/main.py, app/web/routes.py, app/templates/base.html]
tech_stack:
  added: []
  patterns: [sqlalchemy-case-expression, jsonb-score-extraction, alpinejs-global-store, htmx-partial-loading]
key_files:
  created:
    - app/api/v1/analytics.py
    - app/templates/pages/analytics.html
    - app/templates/partials/_analytics_metrics.html
    - app/templates/partials/_analytics_by_source.html
    - app/templates/partials/_analytics_routing.html
    - app/templates/partials/_analytics_scores.html
    - app/templates/partials/_batch_action_bar.html
  modified:
    - app/main.py
    - app/web/routes.py
    - app/templates/base.html
    - app/templates/partials/_review_card.html
    - app/templates/partials/_review_list.html
decisions:
  - Analytics page uses single-column scrollable layout (not 3-column like audit cockpit)
  - Metrics partial combines summary cards + by-source/phase tables in one HTMX load
  - Batch mode uses Alpine.js global store for cross-component state sharing
  - Batch operations use fetch() API instead of HTMX form for dynamic JSON payload
  - Avg wait time calculated via earliest_subq+decision_subq JOIN pattern (not hardcoded)
metrics:
  duration: 11m
  completed: 2026-05-18
  tasks: 2
  files: 13
---

# Phase 25 Plan 01: Analytics Dashboard Summary

Analytics dashboard with approval/rejection rates, routing ratio visualization, AI score distribution histogram, and V1 batch review UI.

## One-liner

Three-endpoint analytics API + dashboard page with real avg wait time, AUTO/HUMAN routing bar, score histogram, and batch approve/reject UI for V1 reviews.

## Commits

| Commit | Message |
|--------|---------|
| `25f5801` | feat(25-01): analytics API endpoints and dashboard page |
| `2e7d235` | feat(25-01): V1 batch review UI entry point |

## Task Results

### Task 1: Analytics API endpoints and dashboard page

**Status:** Complete
**Commit:** `25f5801`

Created three analytics aggregation endpoints at `/api/v1/analytics/`:
- `GET /summary` -- total decisions, approval rate, avg wait time (real calculation), daily throughput, by-source/phase breakdowns
- `GET /routing-ratio` -- AUTO/HUMAN/AI_AUDIT/BLOCK counts and percentages from ShotCard data
- `GET /score-distribution` -- 5-bucket AI score histogram from narrative_context JSONB

Created `/analytics` dashboard page with:
- Date range picker with Today/7d/30d/All quick-select buttons
- Alpine.js state management for date range and partial refresh
- Three HTMX-loaded sections: metrics, routing, scores

Created four partials:
- `_analytics_metrics.html` -- summary cards (total, rate, wait time), daily throughput chart, by-source/phase tables with ratio bars
- `_analytics_routing.html` -- horizontal stacked bar with color-coded legend
- `_analytics_scores.html` -- vertical bar histogram with 5 color-coded buckets

Fixed hardcoded `avg_decision_time = 0.0` in existing `audit_stats_partial` route with real earliest_subq + decision_subq calculation.

Added Analytics tab to bottom navigation bar in `base.html`.

### Task 2: V1 batch review UI entry point

**Status:** Complete
**Commit:** `2e7d235`

Modified `_review_card.html` to show batch selection checkboxes when Alpine.js `$store.batch.active` is true. Checkboxes use `x-model` bound to `$store.batch.selectedIds`.

Modified `_review_list.html` to include batch mode toggle button and Alpine.js global store initialization. Includes `_batch_action_bar.html` conditionally.

Created `_batch_action_bar.html` -- fixed bottom bar with:
- Selected count display
- Optional comment input
- Batch Approve (green) and Batch Reject (red) buttons
- Cancel button to clear selection

Added two HTMX routes:
- `POST /reviews/batch/approve-htmx` -- validates review_ids (max 100), calls transition_state per review, returns result HTML
- `POST /reviews/batch/reject-htmx` -- same pattern with reject action and reason

Both routes trigger `review_status` SSE event for auto-refresh and show per-item success/failure feedback.

## Deviations from Plan

None -- plan executed exactly as written.

## Threat Mitigations Applied

| Threat ID | Mitigation | Status |
|-----------|-----------|--------|
| T-25-01 | Date range validated via `date.fromisoformat()`, clamped to max 365 days | Applied |
| T-25-02 | review_ids validated as int list, max 100 items, user authenticated | Applied |
| T-25-03 | All analytics routes require `get_template_user` auth, reject ai_service | Applied |

## Self-Check: PASSED

- All 7 created files verified present
- Both commit hashes verified in git log
- All endpoints import cleanly
- No new packages in requirements.txt
