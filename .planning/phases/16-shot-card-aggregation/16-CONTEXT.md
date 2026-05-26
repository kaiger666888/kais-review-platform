# Phase 16: Shot Card Aggregation - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase)

<domain>
## Phase Boundary

Node outputs from an AI pipeline progressively assemble into Shot Cards, with visual bundles displaying first and audio appending when ready. This phase builds the Shot Card Aggregator, Topology Collapser, and Progressive Fill engine on top of the Foundation data model from Phase 15.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Key references:
- `.planning/research/V2-ARCHITECTURE.md` — Shot Card aggregator design, topology collapser, progressive fill
- `.planning/research/V2-GAP-ANALYSIS.md` — GAP-2.2 (Aggregator), GAP-2.9 (Topology Collapser)
- `app/models/shot_card.py` — Shot Card SQLAlchemy model created in Phase 15
- `app/core/events.py` — V1 event manager (extendable for progressive fill events)

### Pre-established Decisions
- OpenClaw integration is out of scope — use mock events for testing
- Shot Card aggregation is event-driven (listen to node completion events)
- Progressive fill: visual_bundle first, audio_bundle independently
- min_audit_set logic determines when review is unlocked
- Events should include: node_completed, bundle_ready, shot_card_updated

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models/shot_card.py` — ShotCard SQLAlchemy model with JSONB columns
- `app/models/schemas.py` — Pydantic models for ShotCard
- `app/core/events.py` — EventManager with asyncio.Queue-based SSE broadcast
- `app/core/database.py` — PostgreSQL async engine

### Integration Points
- Aggregator receives node completion events and writes to Shot Card
- Progressive fill updates Shot Card JSONB fields incrementally
- min_audit_set unlock triggers event for review UI

</code_context>

<specifics>
## Specific Ideas

Follow V2 architecture spec for aggregator topology collapser pattern.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.
