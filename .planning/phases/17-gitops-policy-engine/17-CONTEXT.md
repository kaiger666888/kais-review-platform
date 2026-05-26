# Phase 17: GitOps Policy Engine - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase)

<domain>
## Phase Boundary

Policy decisions are driven by Git-versioned rule files, with every Shot Card carrying the exact policy commit SHA that evaluated it. This phase enhances the policy engine to accept Shot Card input, support policy stacking (global+project+temporary), and integrate with Git for policy-as-code.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion. Key references:
- `.planning/research/V2-ARCHITECTURE.md` — GitOps version control plane, policy engine design
- `.planning/research/V2-GAP-ANALYSIS.md` — GAP-1.1 (Git integration), GAP-1.2 (Policy-as-code), GAP-1.3 (Provenance), GAP-2.3 (Enhanced policy engine)
- `app/core/policy.py` — V1 policy engine (extend for Shot Card input)
- `app/models/shot_card.py` — ShotCard model with provenance field
- `app/policies/default.yaml` — V1 YAML policy format

### Pre-established Decisions
- GitPython for Git repo integration (already in requirements.txt from Phase 15)
- Policy stacking: global → project → temporary, last match wins
- Shot Card as input: use narrative_context (continuity_tags, emotion_curve) in rule evaluation
- Provenance tracking: policy_commit_sha, workflow_version, execution_id on every Shot Card
- No application restart needed for policy changes — read from Git on each evaluation

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/core/policy.py` — V1 PolicyEngine with YAML + JSON Schema validation + AND/OR evaluation
- `app/policies/default.yaml` — V1 YAML policy format with risk thresholds
- `app/models/shot_card.py` — ShotCard model with provenance JSONB field
- `app/core/config.py` — Settings with git_repo_url, git_branch config fields

### Integration Points
- Policy engine called by aggregator after Shot Card assembly
- Provenance fields written back to Shot Card after evaluation
- Audit records must reference policy_commit_sha

</code_context>

<specifics>
## Specific Ideas

Follow V2 architecture spec for GitOps policy layer. Extend V1 PolicyEngine rather than rewrite.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.
