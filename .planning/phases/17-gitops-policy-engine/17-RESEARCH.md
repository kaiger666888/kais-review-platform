# Phase 17 Research: GitOps Policy Engine

**Researched:** 2026-05-16
**Status:** Complete

## Research Questions

### R1: How to extend V1 PolicyEngine to accept Shot Card (not flat dict)

**Finding:** The V1 `PolicyEngine.evaluate()` takes a flat `dict` as `review_data`. The `_evaluate_check()` method resolves dotted field paths (e.g., `metadata.flagged`) via nested dict traversal. This is a natural fit for Shot Card's nested JSONB structure.

**Approach:** Rather than passing the entire ShotCard SQLAlchemy model, we flatten the Shot Card into an evaluation dict with namespaced keys:
- `narrative_context.scene`, `narrative_context.emotion_curve`, `narrative_context.continuity_tags`
- `project_id`, `shot_id`
- `audit_status`, `routing_decision`
- `visual_bundle.keyframes.first` (if present)

The existing dotted-path resolver in `_evaluate_check()` already handles this perfectly. We add a `ShotCardPolicyEngine` subclass that:
1. Accepts a `ShotCard` model instance
2. Converts it to an evaluation dict via `_shot_card_to_eval_dict()`
3. Delegates to parent `evaluate()` with the flattened dict

No changes to the core condition evaluation logic needed.

### R2: Policy stacking implementation

**Finding:** V1 `PolicyEngine` loads multiple policies by name and evaluates them in alphabetical order. This is close but not sufficient for "global -> project -> temporary" stacking with precedence.

**Approach:** Introduce a `PolicyStack` concept with three layers:
1. **global**: Policies from `policies/global/` in the Git repo (evaluated first)
2. **project**: Policies from `policies/projects/{project_id}/` (evaluated second)
3. **temporary**: Policies from `policies/temporary/` (evaluated last, highest precedence)

Precedence rule: **Last match wins**. Each layer's rules are appended to the evaluation list in order. The final matching rule across all layers determines the disposition.

Implementation: `evaluate_with_stack(shot_card, project_id)` method that:
1. Collects all applicable policies from global, then project, then temporary layers
2. Sorts rules by priority within each layer
3. Evaluates in order, last match wins (or first match wins per layer, with later layers overriding)

### R3: GitPython integration

**Finding:** `gitpython==3.1.50` is in `requirements.txt`. GitPython provides:
- `git.Repo.clone_from(url, path)` for initial clone
- `repo.remotes.origin.fetch()` for updates
- `repo.commit(sha)` to get a specific commit
- `commit.tree` to browse files at that commit
- `commit.hexsha` for the full SHA
- `repo.head.commit.hexsha` for current HEAD SHA
- `blob.data_stream.read().decode()` to read file contents at a commit

**Approach:** Create a `GitPolicyProvider` class:
1. On startup or evaluation: clone/fetch the governance repo to a local directory
2. Read YAML policy files from `repo.commit(head).tree / "policies" / ...`
3. Return `(policies_dict, commit_sha)` tuple
4. Cache by commit SHA — if HEAD hasn't changed, use cached policies
5. Use a filelock or asyncio.Lock to prevent concurrent clone/fetch operations

The provider does NOT write to the repo (read-only). PR-based policy changes happen externally.

**Key GitPython patterns:**
```python
import git

repo = git.Repo.clone_from(url, local_path, branch="main")
# or repo = git.Repo(local_path); repo.remotes.origin.pull()

head_sha = repo.head.commit.hexsha
tree = repo.head.commit.tree

# Read a file at HEAD
blob = tree["policies"]["global"]["routing.yaml"]
content = blob.data_stream.read().decode("utf-8")

# Read at specific commit
commit = repo.commit(sha)
blob = commit.tree["policies"]["global"]["routing.yaml"]
```

### R4: Provenance tracking

**Finding:** The `ShotCard` model already has provenance columns:
- `workflow_version: Mapped[str | None]`
- `policy_commit_sha: Mapped[str | None]`
- `execution_id: Mapped[str | None]`

The `ShotCardAggregator._ensure_shot_card()` already populates these from the event's provenance dict.

**Approach:** After policy evaluation, write the `policy_commit_sha` back to the ShotCard:
1. `GitPolicyProvider` returns `(policies, commit_sha)` after reading from Git
2. `ShotCardPolicyEngine.evaluate_with_stack()` returns `(disposition, policy_commit_sha, matched_rules_log)`
3. Aggregator (or a new orchestration layer) writes `policy_commit_sha` to the ShotCard
4. The `execution_id` and `workflow_version` come from the event's provenance (already wired)

For audit trail: create an AuditEntry with the `policy_commit_sha` and `matched_rules` in the payload.

### R5: Caching policy evaluation with Git commit SHA as cache key

**Finding:** Policy evaluation is fast (in-memory dict traversal), but Git operations (fetch + read blobs) can be slow (network).

**Approach:** Two-level cache:
1. **Policy content cache**: `dict[str, list[dict]]` keyed by `commit_sha` — parsed YAML policies for a given commit. In-memory, no TTL needed (commit SHAs are immutable).
2. **HEAD SHA cache**: Store the last known HEAD SHA. On each evaluation, compare current HEAD to cached HEAD. If same, reuse cached policies. Only fetch when needed.

This avoids redundant Git fetches. The cache invalidates automatically when the repo advances to a new commit.

**Flow:**
```
evaluate(shot_card, project_id) ->
  current_sha = get_cached_or_fetch_head_sha()
  if current_sha == cached_sha:
    policies = policy_cache[cached_sha]
  else:
    policies = read_policies_from_git(current_sha)
    policy_cache[current_sha] = policies
    cached_sha = current_sha
  result = evaluate_policies(shot_card, policies)
  return (result, current_sha)
```

## Architecture Decision: Extend V1 PolicyEngine

The V1 PolicyEngine is well-tested (54 tests in test_policy_engine.py) with solid AND/OR evaluation, dotted field access, and JSON Schema validation. Rather than rewrite, we:

1. **Keep** `app/core/policy.py` as-is (V1 `PolicyEngine` class unchanged)
2. **Add** `app/core/policy_v2.py` with `ShotCardPolicyEngine(PolicyEngine)` that adds:
   - `_shot_card_to_eval_dict()` — converts ShotCard model to flat evaluation dict
   - `evaluate_shot_card(shot_card, project_id=None)` — evaluates with Shot Card awareness
   - `evaluate_with_stack(shot_card, project_id)` — policy stacking evaluation
3. **Add** `app/services/git_policy_provider.py` with `GitPolicyProvider` that:
   - Manages the local Git repo clone
   - Reads policies at specific commits
   - Caches by commit SHA
   - Returns `(policies, commit_sha)` tuples
4. **Wire** into the aggregation pipeline: after progressive fill + min_audit_set satisfied, evaluate policy and write provenance

## File Impact Summary

| File | Action | Purpose |
|------|--------|---------|
| `app/core/policy_v2.py` | CREATE | ShotCardPolicyEngine extending V1, policy stacking, evaluation dict converter |
| `app/services/git_policy_provider.py` | CREATE | Git repo management, policy file reading, SHA-based caching |
| `app/services/aggregator.py` | MODIFY | Wire policy evaluation after min_audit_set satisfied, write provenance |
| `app/models/shot_card.py` | NO CHANGE | Provenance fields already exist |
| `app/core/config.py` | NO CHANGE | git_repo_url, git_branch already exist |
| `app/core/policy.py` | NO CHANGE | V1 PolicyEngine kept as-is for backward compatibility |
| `app/policies/` | KEEP | V1 policies still work as fallback |
| `tests/test_policy_engine.py` | KEEP | V1 tests remain valid |
| `tests/test_policy_v2.py` | CREATE | Tests for ShotCard evaluation, stacking, narrative context |
| `tests/test_git_policy_provider.py` | CREATE | Tests for Git provider with mock repo |

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Git repo unavailable at startup | Fallback to local `app/policies/` V1 policies. Log warning. |
| Large policy files slow to parse | In-memory cache by SHA. YAML parsing is fast. |
| Concurrent Git operations | asyncio.Lock on fetch operations |
| GitPython memory usage | Repo object kept alive, only fetch() on update (not re-clone) |
| Narrative context fields missing | Evaluation dict includes optional fields as None; conditions fail gracefully (existing V1 behavior) |
