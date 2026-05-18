---
phase: 23-review-template-system
plan: 01
subsystem: core/template_registry
tags: [yaml, jsonschema, template-engine, review-ui]
dependency_graph:
  requires: [app/core/policy.py, app/models/shot_card.py]
  provides: [TemplateRegistry, TemplateConfig, derive_source_system, get_template_registry]
  affects: []
tech_stack:
  added: []
  patterns: [YAML config loading, JSON Schema validation, frozen dataclass, module-level singleton]
key_files:
  created:
    - app/core/template_registry.py
    - app/templates/config/default.yaml
    - app/templates/config/movie-agent.yaml
    - app/templates/config/gold-team.yaml
    - tests/test_template_registry.py
  modified: []
decisions:
  - Mirror PolicyEngine pattern for consistency (yaml.safe_load + jsonschema.validate + load_from_directory)
  - TemplateConfig as frozen dataclass for immutability
  - 3-level fallback chain: exact phase -> source _default -> global default
  - Path traversal mitigation via partials/ prefix validation
  - derive_source_system checks narrative_context first, then project_id prefix convention
metrics:
  duration: 224s
  completed: 2026-05-18
  tasks: 2
  files: 5
---

# Phase 23 Plan 01: Template Registry Engine Summary

TemplateRegistry engine with YAML config loading, JSON Schema validation, source_system + phase resolution with 3-level fallback, and path traversal security -- powering per-source review UI layouts.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | TemplateRegistry engine (TDD) | c2a9799 + 6e37227 | app/core/template_registry.py, tests/test_template_registry.py |
| 2 | YAML template config files | 8227462 | app/templates/config/default.yaml, movie-agent.yaml, gold-team.yaml |

## Task Details

### Task 1: TemplateRegistry Engine (TDD)

**TDD cycle:**
- RED (c2a9799): 16 unit tests covering all 11 specified behaviors plus additional edge cases
- GREEN (6e37227): Full TemplateRegistry implementation passing all 16 tests

**Implementation highlights:**
- `TemplateRegistry` class with `validate_template`, `load_from_file`, `load_from_directory`, `resolve`, `list_templates`
- `TEMPLATE_JSON_SCHEMA` dict enforcing required fields (name, version, source_system, templates) and per-phase desktop/mobile structure
- `_validate_include_paths` security check: all decision_panel/media_player paths must start with `partials/`
- `TemplateConfig` frozen dataclass with sensible defaults (grid layout, standard partials)
- `derive_source_system` standalone function: narrative_context.source_system -> project_id prefix -> "unknown"
- Module-level singleton via `get_template_registry()`

### Task 2: YAML Template Config Files

**default.yaml:** Fallback template with standard decision_panel + media_player layout, grid candidates, no scores.

**movie-agent.yaml:** 6 phase templates:
- art-direction: side-by-side candidates, scores shown, candidate grid partial
- character: grid candidates, scores shown, candidate grid partial
- voice: no candidates, no scores, standard decision panel
- scene: scores shown, no candidates, standard decision panel
- storyboard: grid candidates, scores shown, candidate grid partial
- quality-gate: scores shown, no candidates, standard decision panel
- _default: standard layout as source-level fallback

**gold-team.yaml:** task-parameter template with risk assessment partial, no candidates/scores, plus _default fallback.

## Verification Results

```
16 passed in 0.11s
```

All acceptance criteria verified:
- default.yaml: source_system: default with _default template entry
- movie-agent.yaml: source_system: kais-movie-agent with art-direction and quality-gate entries
- art-direction: show_scores=true, candidate_layout=side-by-side, show_candidates=true
- quality-gate: show_scores=true, show_candidates=false
- gold-team.yaml: source_system: kais-gold-team with task-parameter entry
- task-parameter: decision_panel references partials/_template_risk_assessment.html
- All three YAML files pass TEMPLATE_JSON_SCHEMA validation

## Decisions Made

1. **Frozen dataclass for TemplateConfig** -- immutability prevents accidental mutation during resolve chain
2. **Pattern Properties in JSON Schema** -- allows flexible phase names (alphanumeric + dash + underscore) while still validating structure
3. **3-level fallback chain** -- mirrors HTTP content negotiation pattern: specific -> generic -> global default

## Deviations from Plan

None -- plan executed exactly as written.

## TDD Gate Compliance

- [x] RED gate commit exists: c2a9799 `test(23-01): add failing tests for TemplateRegistry engine`
- [x] GREEN gate commit exists: 6e37227 `feat(23-01): implement TemplateRegistry engine with YAML loading and resolve`
- [x] REFACTOR: not needed -- implementation is clean on first pass

## Self-Check: PASSED

All 5 created files verified present. All 3 commit hashes verified in git log.
