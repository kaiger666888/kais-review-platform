---
phase: 23-review-template-system
plan: 02
subsystem: core/template_rendering
tags: [jinja2, htmx, alpinejs, template-registry, mobile-api]

# Dependency graph
requires:
  - phase: 23-01
    provides: TemplateRegistry, TemplateConfig, derive_source_system, get_template_registry, YAML configs
provides:
  - _template_wrapper.html for dynamic Jinja2 include selection
  - _template_candidate_grid.html for movie-agent candidate display
  - _template_risk_assessment.html for gold-team risk display
  - template_config in MobileShotCardBundle for mobile conditional rendering
  - Template-aware shot_card_detail_partial handler
  - Template registry initialization at startup
affects: [desktop-workstation, mobile-pwa]

# Tech tracking
tech-stack:
  added: []
  patterns: [dynamic Jinja2 include via TemplateConfig, template-aware route handler, mobile API template metadata]

key-files:
  created:
    - app/templates/partials/_template_wrapper.html
    - app/templates/partials/_template_candidate_grid.html
    - app/templates/partials/_template_risk_assessment.html
    - tests/test_template_rendering.py
  modified:
    - app/web/routes.py
    - app/models/schemas.py
    - app/api/v1/mobile.py
    - app/templates/partials/_mobile_card.html
    - app/main.py

key-decisions:
  - "Template wrapper uses Jinja2 dynamic include with ignore missing for graceful fallback"
  - "Mobile template_config is a dict (not TemplateConfig) for JSON serialization compatibility"
  - "Template registry loaded at startup alongside policy engine in lifespan"

patterns-established:
  - "Template-aware route handler: derive source_system -> resolve phase -> render wrapper"
  - "Mobile template metadata injection: _shot_card_to_bundle resolves template_config inline"
  - "Conditional mobile rendering via Alpine.js template_config.card_variant checks"

requirements-completed: [INTEGRATION-4B.1]

# Metrics
duration: 10min
completed: 2026-05-18
---

# Phase 23 Plan 02: Template Rendering Integration Summary

**TemplateRegistry wired into desktop routes and mobile API with source_system + phase resolution, movie-agent candidate grid, gold-team risk assessment partials, and mobile template_config metadata**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-18T06:10:15Z
- **Completed:** 2026-05-18T06:20:37Z
- **Tasks:** 1
- **Files modified:** 9

## Accomplishments
- Desktop shot_card_detail_partial uses TemplateRegistry to dynamically select partials based on source_system + phase
- Movie-agent art-direction/character/storyboard phases render candidate grid with side-by-side layout, score badges, and select+approve buttons
- Gold-team task-parameter phase renders risk assessment with task type badge, parameter list, and color-coded progress bar
- Mobile API returns template_config dict (card_variant, show_scores, show_candidates) in every MobileShotCardBundle
- Mobile card template conditionally renders risk bar overlay and score display based on card_variant
- Template configs loaded at application startup from app/templates/config/ directory

## Task Commits

TDD cycle (single task):

1. **Task 1 (RED): Failing tests for template-aware rendering** - `caf241a` (test)
2. **Task 1 (GREEN): Wire TemplateRegistry into desktop and mobile** - `2091eda` (feat)

## Files Created/Modified
- `app/templates/partials/_template_wrapper.html` - Dynamic Jinja2 wrapper that includes template-selected partials with OOB media swap
- `app/templates/partials/_template_candidate_grid.html` - Movie-agent candidate grid with side-by-side/grid layout, score badges, selection buttons
- `app/templates/partials/_template_risk_assessment.html` - Gold-team risk assessment with task params, color-coded risk bar, approve/reject
- `app/web/routes.py` - shot_card_detail_partial now resolves template and renders via wrapper
- `app/models/schemas.py` - MobileShotCardBundle.template_config: dict | None field added
- `app/api/v1/mobile.py` - _shot_card_to_bundle populates template_config from registry
- `app/templates/partials/_mobile_card.html` - Conditional risk bar and candidate score display
- `app/main.py` - Template registry loaded at startup in lifespan
- `tests/test_template_rendering.py` - 13 integration tests for template resolution and rendering

## Decisions Made
- Used MagicMock for ShotCard in integration tests since PostgreSQL JSONB type is incompatible with SQLite test engine
- Template wrapper uses `ignore missing` on Jinja2 includes for graceful degradation if a partial is absent
- Mobile template_config is a plain dict (not TemplateConfig dataclass) for clean JSON serialization
- OOB media swap kept inside template wrapper, consistent with existing _decision_panel.html pattern

## Deviations from Plan

None -- plan executed exactly as written.

## TDD Gate Compliance

- [x] RED gate commit exists: caf241a `test(23-02): add failing tests for template-aware rendering`
- [x] GREEN gate commit exists: 2091eda `feat(23-02): wire TemplateRegistry into desktop and mobile rendering`
- [x] REFACTOR: not needed -- implementation is clean on first pass

## Test Results

```
29 passed in 0.34s (test_template_rendering.py + test_template_registry.py)
430 passed, 2 failed (full suite -- 2 pre-existing failures unrelated to this change)
```

## Next Phase Readiness
- Template-aware rendering fully operational for desktop workstation and mobile PWA
- Ready for Phase 23 Plan 03 if additional template variants are needed
- YAML template configs can be extended with new source_systems or phases without code changes

---
*Phase: 23-review-template-system*
*Completed: 2026-05-18*
