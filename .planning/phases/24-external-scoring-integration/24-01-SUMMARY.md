---
phase: 24-external-scoring-integration
plan: 01
subsystem: external-scoring
tags: [ai-score, narrative-context, mobile-bundle, template-rendering, jsonb]
dependency_graph:
  requires: [phase-23-template-system]
  provides: [ai_score-fields, score-display]
  affects: [schemas, mobile-api, desktop-templates, mobile-templates]
tech_stack:
  added: []
  patterns: [JSONB-nested-score-storage, template-conditional-display, alpine-reactive-badge]
key_files:
  created:
    - tests/test_external_scoring.py
  modified:
    - app/models/schemas.py
    - app/api/v1/mobile.py
    - app/templates/partials/_decision_panel.html
    - app/templates/partials/_template_candidate_grid.html
    - app/templates/partials/_mobile_card.html
decisions:
  - "Store ai_score fields in narrative_context JSONB (no new columns)"
  - "ai_score_dimensions is free-form dict (not typed model) to avoid hardcoding dimension names"
  - "Color thresholds: green >= 70, yellow >= 50, red < 50"
  - "Test assertions check visible h3 headings not HTML comments"
metrics:
  duration: "5m 44s"
  completed: "2026-05-18"
  tasks: 2
  files: 6
  tests_added: 11
  tests_passed: 11
  regressions: 0
---

# Phase 24 Plan 01: External Scoring Integration Summary

Extended NarrativeContext and MobileShotCardBundle with optional AI score fields from movie-agent; added read-only score panels to desktop decision panels and mobile card detail view.

## What Changed

### Schema Extension (Task 1)
- `NarrativeContext` gained 3 optional fields: `ai_score` (int), `ai_score_dimensions` (dict), `ai_score_source` (str) -- all default None
- `MobileShotCardBundle` gained the same 3 optional fields for mobile API responses
- `_shot_card_to_bundle()` in `mobile.py` extracts score fields from `narrative_context` JSONB using safe `.get()` calls
- No database migration needed -- JSONB columns are schema-flexible

### Template Rendering (Task 2)
- `_decision_panel.html`: AI Score section between Node Status and Provenance, gated by `template.show_scores` and `nc.get('ai_score') is not none`
- `_template_candidate_grid.html`: Identical AI Score panel between Node Status and Provenance
- `_mobile_card.html`: Alpine.js AI score badge in detail panel between Visual Prompt and Audio, gated by `template_config.show_scores && ai_score != null`
- All panels render overall score + dimension breakdown (dynamic `dict.items()` iteration) + source
- Color coding: green >= 70, yellow >= 50, red < 50

## Commits

| Commit | Message | Type |
|--------|---------|------|
| `5057c61` | test(24-01): add failing tests for external AI score integration | TDD RED |
| `c3dbfdf` | feat(24-01): extend schemas and mobile bundle for external AI scores | TDD GREEN |
| `a39888c` | feat(24-01): render AI score panels in desktop and mobile review UI | TDD GREEN |

## Test Coverage

| Test | Description | Status |
|------|-------------|--------|
| Test 1 | NarrativeContext accepts optional ai_score fields (all None defaults) | PASSED |
| Test 2 | NarrativeContext with ai_score=72 serializes correctly | PASSED |
| Test 3 | MobileShotCardBundle accepts optional ai_score fields | PASSED |
| Test 4 | _shot_card_to_bundle extracts ai_score from narrative_context | PASSED |
| Test 5 | _shot_card_to_bundle returns None when no score keys | PASSED |
| Test 6 | ShotCardCreate with ai_score passes validation | PASSED |
| Test 7 | _decision_panel.html renders AI Score when show_scores=true | PASSED |
| Test 8 | _decision_panel.html hides AI Score when show_scores=false | PASSED |
| Test 9 | _decision_panel.html hides AI Score when no ai_score data | PASSED |
| Test 10 | _mobile_card.html has ai_score badge with show_scores gate | PASSED |
| Test 11 | _template_candidate_grid.html renders ShotCard-level AI Score | PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion matched HTML comment instead of visible heading**
- **Found during:** Task 2 GREEN phase
- **Issue:** Tests 8-9 used `assert "AI Score" not in html` which matched the HTML comment `<!-- AI Score (...) -->` that Jinja2 renders unconditionally, causing false test failures
- **Fix:** Changed assertions to check for the visible `<h3>` heading element: `assert '<h3 class="text-xs font-semibold uppercase text-gray-500">AI Score</h3>' not in html`
- **Files modified:** `tests/test_external_scoring.py`
- **Commit:** `a39888c`

## Pre-existing Issues (Out of Scope)

2 test failures existed before this phase, unrelated to scoring changes:
1. `test_policy_integration.py::test_evaluate_policy_calls_git_provider` -- `evaluate_with_stack()` argument mismatch
2. `test_token_endpoint.py::test_token_endpoint_returns_200_with_valid_jwt` -- `ReviewTokenResponse` missing `expires_at` field

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (failing tests) | `5057c61` | Verified -- first test failed with AttributeError |
| GREEN (implementation) | `c3dbfdf` + `a39888c` | Verified -- all 11 tests pass |
| REFACTOR | N/A | No refactoring needed |

## Success Criteria Verification

1. Review submission API accepts `metadata.ai_score` -- already works via free-form JSONB, no code change needed
2. `ShotCardCreate` accepts `narrative_context` with ai_score fields -- validated by NarrativeContext schema (Test 6)
3. `ShotCardResponse` returns ai_score fields inside `narrative_context` dict -- implicit (JSONB passthrough)
4. `MobileShotCardBundle` returns flat ai_score fields in mobile API responses -- verified (Tests 3-4)
5. Desktop decision panel renders AI Score when `template.show_scores=true` -- verified (Test 7)
6. Mobile card renders AI score badge when `template_config.show_scores=true` -- verified (Test 10)
7. No score computation logic in review-platform code -- confirmed (storage + display only)

## Self-Check: PASSED

All 6 modified/created files verified present. All 3 commits verified in git log.
