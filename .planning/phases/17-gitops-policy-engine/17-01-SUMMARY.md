---
phase: 17-gitops-policy-engine
plan: 01
subsystem: policy-engine
tags: [yaml, gitpython, policy-stacking, shot-card, gitops, provenance]

# Dependency graph
requires:
  - phase: 15-foundation
    provides: ShotCard SQLAlchemy model, V2 Settings with git_repo_url/git_branch, GitPython in requirements.txt
  - phase: 16-shot-card-aggregation
    provides: Aggregator service, narrative_context JSONB field structure
provides:
  - ShotCardPolicyEngine class extending V1 PolicyEngine for Shot Card evaluation
  - PolicyResult dataclass with disposition, policy_commit_sha, matched_rule, stack_layers_evaluated
  - Policy stacking: global -> project -> temporary, last match wins precedence
  - GitPolicyProvider with SHA-based caching and local fallback
  - 31 new tests (18 policy V2 + 13 git provider)
affects: [17-02, 18-routing, 22-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Policy stacking: layered evaluation global->project->temporary with last-match-wins"
    - "SHA-based caching: Git commit SHA as cache key for immutable policy snapshots"
    - "asyncio.Lock for concurrent Git operation serialization"

key-files:
  created:
    - app/core/policy_v2.py
    - app/services/git_policy_provider.py
    - tests/test_policy_v2.py
    - tests/test_git_policy_provider.py
  modified:
    - app/models/schemas.py

key-decisions:
  - "Re-added Disposition enum to schemas.py for V1 policy.py backward compatibility"
  - "ShotCardPolicyEngine inherits from V1 PolicyEngine rather than replacing it"
  - "GitPolicyProvider uses MockTree/MockBlob patterns for test isolation from GitPython"

patterns-established:
  - "TDD for policy engine: RED test commit, GREEN implementation commit"
  - "MockBlob/MockTree test helpers for simulating Git tree traversal"

requirements-completed: [POL-01, POL-02]

# Metrics
duration: 12min
completed: 2026-05-16
---

# Phase 17 Plan 01: GitOps Policy Engine Foundation Summary

**ShotCardPolicyEngine with Shot Card evaluation and policy stacking (global/project/temporary precedence), plus GitPolicyProvider with SHA-based Git commit caching and local fallback**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-16T11:17:40Z
- **Completed:** 2026-05-16T11:30:27Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- ShotCardPolicyEngine evaluates ShotCard objects using narrative_context fields (emotion_curve, continuity_tags, scene) via inherited dotted-path resolution
- Policy stacking implements global -> project -> temporary layers with deterministic last-match-wins precedence
- PolicyResult dataclass tracks disposition, policy_commit_sha, matched_rule, and evaluated layers for full provenance
- GitPolicyProvider reads versioned YAML policies from Git governance repo at specific commits with SHA-based caching
- Fallback to local app/policies/ directory when git_repo_url is empty (V1 backward compat)
- All 31 new tests pass, all 42 V1 tests pass (73 total, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: ShotCardPolicyEngine tests** - `934aafe` (test)
2. **Task 1 GREEN: ShotCardPolicyEngine implementation** - `a4c2bd0` (feat)
3. **Task 2 RED: GitPolicyProvider tests** - `d9022bd` (test)
4. **Task 2 GREEN: GitPolicyProvider implementation** - `e98e73a` (feat)

## Files Created/Modified
- `app/core/policy_v2.py` - ShotCardPolicyEngine extending V1 PolicyEngine, PolicyResult dataclass, policy stacking evaluation
- `app/services/git_policy_provider.py` - GitPolicyProvider with SHA caching, Git tree reading, local fallback, singleton factory
- `tests/test_policy_v2.py` - 18 tests: ShotCard-to-eval-dict conversion, evaluate_shot_card, policy stacking, load_policies_from_layer
- `tests/test_git_policy_provider.py` - 13 tests: init, get_policies, SHA caching, project policies, commit-specific reads, fallback, concurrent access
- `app/models/schemas.py` - Re-added Disposition enum for V1 policy.py backward compatibility

## Decisions Made
- Re-added Disposition enum to schemas.py (was removed in V2 migration but V1 policy.py still imports it) -- minimal backward-compat bridge until V1 policy engine is fully deprecated
- ShotCardPolicyEngine inherits from V1 PolicyEngine, not a rewrite -- preserves all 42 existing tests and the proven condition evaluation logic
- GitPolicyProvider uses MockTree/MockBlob test helpers rather than real GitPython objects for fast, isolated tests

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Re-added Disposition enum to schemas.py**
- **Found during:** Task 1 (ShotCardPolicyEngine implementation)
- **Issue:** V2 migration removed Disposition enum from app/models/schemas.py, but V1 app/core/policy.py still imports it. Both V1 and V2 policy engine tests failed at collection.
- **Fix:** Added Disposition enum back to schemas.py with same values (AUTO/HUMAN/AI_AUDIT/BLOCK) as backward-compatible alias for RoutingDecision.
- **Files modified:** app/models/schemas.py
- **Verification:** All 42 V1 tests pass, all 18 V2 tests pass
- **Committed in:** a4c2bd0 (Task 1 commit)

**2. [Rule 3 - Blocking] Updated test mock tree structure for 3-level project nesting**
- **Found during:** Task 2 (GitPolicyProvider tests)
- **Issue:** _make_mock_tree helper only supported 2-level nesting but project policies require 3 levels (policies/projects/{project_id}/file.yaml)
- **Fix:** Manually constructed MockTree with proper 3-level nesting in project-specific tests
- **Files modified:** tests/test_git_policy_provider.py
- **Verification:** All 13 git provider tests pass
- **Committed in:** e98e73a (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking issues)
**Impact on plan:** Both fixes were necessary for test execution. No scope creep.

## Issues Encountered
- Worktree was at old commit (6aef75f, pre-Phase 15). Resolved by fetching from local main repo and resetting to 578b01a to include Phase 15-16 code.
- app/services/__init__.py eagerly imports aggregator which triggers database initialization -- not caused by our changes, pre-existing issue. Direct module import works fine.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ShotCardPolicyEngine ready for wiring into aggregator pipeline (Plan 17-02)
- GitPolicyProvider ready for FastAPI lifespan integration
- V1 policy engine fully backward-compatible, zero regressions
- 73 total tests provide solid coverage for both V1 and V2 policy engines

## Self-Check: PASSED

- [x] app/core/policy_v2.py exists
- [x] app/services/git_policy_provider.py exists
- [x] tests/test_policy_v2.py exists
- [x] tests/test_git_policy_provider.py exists
- [x] .planning/phases/17-gitops-policy-engine/17-01-SUMMARY.md exists
- [x] Commit 934aafe (test: ShotCardPolicyEngine RED)
- [x] Commit a4c2bd0 (feat: ShotCardPolicyEngine GREEN)
- [x] Commit d9022bd (test: GitPolicyProvider RED)
- [x] Commit e98e73a (feat: GitPolicyProvider GREEN)

---
*Phase: 17-gitops-policy-engine*
*Completed: 2026-05-16*
