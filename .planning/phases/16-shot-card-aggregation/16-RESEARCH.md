# Phase 16: Shot Card Aggregation - Research

**Researched:** 2026-05-16
**Domain:** Event-driven aggregation, DAG topology collapsing, progressive JSONB fill, min_audit_set logic
**Confidence:** HIGH

## Summary

Phase 16 builds the Shot Card Aggregator -- the event-driven engine that listens for OpenClaw pipeline node completion events, collapses the DAG topology into narrative shot units, and progressively fills Shot Card JSONB fields as outputs arrive. This is the core "fold" from execution topology to review-ready artifact.

The three components to build are: (1) the **Shot Card Aggregator** service that receives node completion events and orchestrates the aggregation pipeline, (2) the **Topology Collapser** that maps DAG node metadata (node type, output kind) to the correct Shot Card bundle fields (visual_bundle, audio_bundle), and (3) the **Progressive Fill Engine** that incrementally updates JSONB columns, checks min_audit_set readiness after each update, and fires events when bundles become ready or the card becomes reviewable. The existing V1 EventManager (`app/core/events.py`) provides the SSE broadcast pattern; this phase extends it with typed progressive fill events.

The core technical challenge is handling **out-of-order completion** -- video clips may arrive before keyframes, audio may arrive before visual. The design must be order-agnostic: any node output can arrive at any time and be merged into the correct position in the Shot Card structure. PostgreSQL `jsonb_set()` via SQLAlchemy `func.jsonb_set()` enables server-side partial JSONB updates without read-modify-write round-trips. SQLAlchemy's `flag_modified()` is the ORM-level equivalent for loaded objects.

**Primary recommendation:** Build a three-layer aggregation service (`app/services/aggregator.py`): Topology Collapser maps node events to bundle fields, Progressive Fill Engine updates JSONB via `flag_modified()`, and the Aggregator orchestrates the flow and fires events. Use a typed event protocol (dataclasses or Pydantic models) for all internal events. Mock OpenClaw events via a test harness API endpoint for development.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- OpenClaw integration is out of scope -- use mock events for testing
- Shot Card aggregation is event-driven (listen to node completion events)
- Progressive fill: visual_bundle first, audio_bundle independently
- min_audit_set logic determines when review is unlocked
- Events should include: node_completed, bundle_ready, shot_card_updated

### Claude's Discretion
All implementation choices are at Claude's discretion -- infrastructure phase. Key references:
- `.planning/research/V2-ARCHITECTURE.md` -- Shot Card aggregator design, topology collapser, progressive fill
- `.planning/research/V2-GAP-ANALYSIS.md` -- GAP-2.2 (Aggregator), GAP-2.9 (Topology Collapser)
- `app/models/shot_card.py` -- Shot Card SQLAlchemy model created in Phase 15
- `app/core/events.py` -- V1 event manager (extendable for progressive fill events)

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SHOT-02 | Shot Card Aggregator -- listen to OpenClaw event bus, group by shot_id, progressive aggregation | Event-driven service pattern with typed events, arq background task for async processing, shot_id as grouping key from node metadata |
| SHOT-03 | Topology Collapser -- map DAG node outputs to Shot Card bundles, handle out-of-order completion | Node type registry mapping (FLUX->keyframes, Wan2.2->video_clip, Audio Prompt->audio_bundle), order-agnostic merge via jsonb_set or dict update + flag_modified |
| SHOT-04 | Progressive Fill -- visual_bundle first, audio_bundle independently, min_audit_set unlock | Incremental JSONB column updates, readiness checker that evaluates min_audit_set list against current bundle state, event emission on state transitions |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.49 | ORM + JSONB updates | Already installed, `flag_modified()` for JSONB mutation detection, `func.jsonb_set()` for server-side partial updates |
| Pydantic | 2.13.3 | Event data models | Already installed, typed event protocol for node_completed/bundle_ready/shot_card_updated |
| redis-py | 5.3.1 | Event pub/sub fan-out | Already installed, `redis.asyncio` pub/sub for cross-process event distribution |
| arq | 0.28.0 | Background task queue | Already installed, async-native, enqueue aggregation processing as arq jobs |
| structlog | (installed) | Structured logging | Already in use, context binding for shot_id/aggregation tracking |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | (stdlib) | Event-driven orchestration | Core async patterns for aggregation pipeline |
| dataclasses | (stdlib) | Lightweight event types | When Pydantic models are overkill for internal events |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `flag_modified()` + dict merge | `func.jsonb_set()` SQL expression | ORM-level simpler to reason about, sufficient for this workload. SQL expression avoids read-modify-write but more complex to compose for nested structures. Use ORM-level for clarity. |
| Redis pub/sub for event routing | Pure in-process asyncio.Queue | Redis pub/sub enables cross-process event distribution (arq worker -> API process). Pure asyncio.Queue only works within a single process. Use Redis pub/sub for decoupled architecture. |
| Pydantic event models | Python dataclasses | Pydantic gives validation + serialization for free. Dataclasses are lighter but no validation. Use Pydantic since event shape is critical for correctness. |
| Single Aggregator class | Separate Collapser + Filler + Aggregator classes | Single class becomes God object with 5+ responsibilities. Three-class separation is cleaner, testable, matches V2 architecture spec. |

**Installation:**
```bash
# No new packages required -- all dependencies already installed from Phase 15
pip list | grep -E "sqlalchemy|pydantic|redis|arq|structlog"
```

**Version verification:**
- SQLAlchemy 2.0.49 -- verified via `pip show`
- Pydantic 2.13.3 -- verified via `pip show`
- redis-py 5.3.1 -- verified via `pip show`
- arq 0.28.0 -- verified via `pip show`

## Architecture Patterns

### Recommended Project Structure
```
app/
├── services/                        # NEW: Business logic services
│   ├── __init__.py
│   ├── aggregator.py                # Shot Card Aggregator orchestrator
│   ├── topology_collapser.py        # DAG node -> Shot Card bundle mapping
│   └── progressive_fill.py          # JSONB incremental update + readiness check
├── core/
│   ├── events.py                    # EXTEND: add progressive fill event types
│   ├── event_types.py               # NEW: typed event protocol definitions
│   └── ...existing...
├── api/v1/
│   ├── shot_cards.py                # NEW: Shot Card CRUD + aggregation trigger endpoint
│   └── ...existing...
├── workers/
│   └── tasks.py                     # EXTEND: add process_node_completion arq task
└── models/
    ├── shot_card.py                 # EXISTS: from Phase 15
    └── schemas.py                   # EXISTS: from Phase 15
```

### Pattern 1: Event-Driven Aggregation Pipeline
**What:** Node completion events flow through a three-stage pipeline: Collapser -> Filler -> Event Emitter
**When to use:** Every node completion event from OpenClaw
**Example:**
```python
# Source: V2-ARCHITECTURE.md section 4.2 + existing event_manager pattern

# app/core/event_types.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class NodeCompletedEvent(BaseModel):
    """OpenClaw node completion event."""
    event_type: Literal["node_completed"] = "node_completed"
    execution_id: str
    shot_id: str
    project_id: str
    node_type: str           # e.g. "FLUX.1-dev", "Wan2.2-T2V", "AudioPrompt"
    node_output: dict        # The actual output data (URLs, metadata)
    narrative_context: dict | None = None  # Populated by first node in shot
    provenance: dict | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class BundleReadyEvent(BaseModel):
    """Fired when a bundle (visual/audio) is complete."""
    event_type: Literal["bundle_ready"] = "bundle_ready"
    shot_id: str
    project_id: str
    bundle_type: Literal["visual_bundle", "audio_bundle"]
    shot_card_id: int

class ShotCardUpdatedEvent(BaseModel):
    """Fired when any Shot Card field changes."""
    event_type: Literal["shot_card_updated"] = "shot_card_updated"
    shot_id: str
    project_id: str
    shot_card_id: int
    updated_fields: list[str]  # Which JSONB fields changed
    min_audit_set_satisfied: bool
    audit_status: str
```

### Pattern 2: Topology Collapser -- Node-to-Bundle Mapping
**What:** Maps DAG node types to Shot Card bundle fields and sub-paths
**When to use:** When receiving any node_completed event
**Example:**
```python
# app/services/topology_collapser.py

# Registry: node_type -> (target_bundle, target_path_within_bundle)
NODE_BUNDLE_MAP = {
    # Visual bundle nodes
    "FLUX.1-dev": ("visual_bundle", "keyframes.first"),    # Text-to-image first frame
    "FLUX.1-dev-t2i": ("visual_bundle", "keyframes.first"),
    "img2img": ("visual_bundle", "keyframes.last"),         # Image-to-image last frame
    "Wan2.2-T2V": ("visual_bundle", "video_clip"),          # Text-to-video
    "PromptNode": ("visual_bundle", "prompt"),               # Visual prompt

    # Audio bundle nodes
    "AudioPrompt": ("audio_bundle", "bgm_prompt"),
    "SFXPrompt": ("audio_bundle", "sfx_prompt"),
    "AudioGen": ("audio_bundle", "status"),                  # Sets status to "ready"

    # Narrative context (from first/orchestrator node)
    "ShotOrchestrator": ("narrative_context", None),         # Full dict, not path
}

class TopologyCollapser:
    """Collapses DAG node outputs into Shot Card bundle structures.

    Order-agnostic: handles video arriving before keyframes,
    audio arriving before visual, etc.
    """

    def collapse(self, node_type: str, node_output: dict) -> dict:
        """Map a single node output to a Shot Card field update.

        Returns dict with:
            target_column: "visual_bundle" | "audio_bundle" | "narrative_context"
            merge_data: dict to merge into the target column
        """
        mapping = NODE_BUNDLE_MAP.get(node_type)
        if mapping is None:
            raise ValueError(f"Unknown node type: {node_type}")

        target_column, path = mapping

        # Build the nested dict structure for this node's contribution
        if target_column == "narrative_context":
            return {"target_column": target_column, "merge_data": node_output}

        if target_column == "visual_bundle":
            merge_data = self._build_visual_merge(path, node_output)
        elif target_column == "audio_bundle":
            merge_data = self._build_audio_merge(path, node_output)
        else:
            raise ValueError(f"Unknown target column: {target_column}")

        return {"target_column": target_column, "merge_data": merge_data}

    def _build_visual_merge(self, path: str, output: dict) -> dict:
        """Build nested dict for visual_bundle path."""
        # e.g. path="keyframes.first" -> {"keyframes": {"first": output}}
        # e.g. path="video_clip" -> {"video_clip": output}
        parts = path.split(".")
        result = output
        for part in reversed(parts):
            result = {part: result}
        return result

    def _build_audio_merge(self, path: str, output: dict) -> dict:
        """Build nested dict for audio_bundle path."""
        parts = path.split(".")
        result = output
        for part in reversed(parts):
            result = {part: result}
        return result
```

### Pattern 3: Progressive Fill -- Incremental JSONB Update
**What:** Merge node output into existing JSONB column, detect mutation for SQLAlchemy
**When to use:** After topology collapse maps a node to a bundle field
**Example:**
```python
# app/services/progressive_fill.py
import structlog
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import async_session_factory
from app.models.shot_card import ShotCard, AuditStatus

logger = structlog.get_logger(__name__)


class ProgressiveFillEngine:
    """Incrementally fills Shot Card JSONB fields as node outputs arrive.

    Handles order-agnostic merging: any field can arrive in any order.
    Uses deep merge to combine new data with existing partial data.
    """

    async def fill(
        self, shot_id: str, target_column: str, merge_data: dict
    ) -> ShotCard | None:
        """Merge data into a Shot Card JSONB column.

        Uses flag_modified() to ensure SQLAlchemy detects the mutation.
        Creates the ShotCard if it doesn't exist (first node for this shot_id).

        Returns:
            Updated ShotCard instance, or None if shot_id not found
            and insufficient data to create.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(ShotCard).where(ShotCard.shot_id == shot_id)
            )
            shot_card = result.scalar_one_or_none()

            if shot_card is None:
                # Cannot fill a non-existent card -- caller must create first
                return None

            # Get current value (may be None for nullable columns)
            current = getattr(shot_card, target_column)
            if current is None:
                current = {}

            # Deep merge new data into existing
            merged = self._deep_merge(current, merge_data)
            setattr(shot_card, target_column, merged)

            # CRITICAL: flag the column as modified for SQLAlchemy dirty tracking
            flag_modified(shot_card, target_column)

            await session.commit()
            await session.refresh(shot_card)

            logger.info(
                "progressive_fill",
                shot_id=shot_id,
                column=target_column,
                fields_updated=list(merge_data.keys()),
            )
            return shot_card

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base dict.

        - Dict values are merged recursively
        - Non-dict values in override replace base values
        - Order-agnostic: partial data accumulates correctly
        """
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ProgressiveFillEngine._deep_merge(
                    result[key], value
                )
            else:
                result[key] = value
        return result

    def check_min_audit_set(self, shot_card: ShotCard) -> bool:
        """Check if the Shot Card's min_audit_set is satisfied.

        min_audit_set is a list of bundle names that must be non-null
        and contain minimum required fields. Default: ["visual_bundle"].

        A bundle is considered 'satisfied' if it is non-null and
        contains at least one key (has any data).
        """
        required = shot_card.min_audit_set or ["visual_bundle"]

        for bundle_name in required:
            bundle = getattr(shot_card, bundle_name, None)
            if bundle is None or not bundle:
                return False

        return True

    def check_bundle_complete(
        self, shot_card: ShotCard, bundle_name: str
    ) -> bool:
        """Check if a specific bundle is fully populated.

        Visual bundle requires: keyframes (first frame) + prompt
        Audio bundle requires: bgm_prompt or sfx_prompt + status != pending
        """
        bundle = getattr(shot_card, bundle_name, None)
        if bundle is None:
            return False

        if bundle_name == "visual_bundle":
            has_keyframes = bundle.get("keyframes") is not None
            has_prompt = bundle.get("prompt") is not None
            return has_keyframes and has_prompt

        if bundle_name == "audio_bundle":
            has_prompts = (
                bundle.get("bgm_prompt") is not None
                or bundle.get("sfx_prompt") is not None
            )
            status = bundle.get("status", "pending")
            return has_prompts and status != "pending"

        return bool(bundle)
```

### Pattern 4: Aggregator Orchestrator
**What:** Top-level service that coordinates collapser, filler, and event emission
**When to use:** Entry point for all node completion events
**Example:**
```python
# app/services/aggregator.py
import structlog

from app.services.topology_collapser import TopologyCollapser
from app.services.progressive_fill import ProgressiveFillEngine
from app.core.events import event_manager

logger = structlog.get_logger(__name__)


class ShotCardAggregator:
    """Orchestrates the aggregation pipeline for node completion events.

    Pipeline: node_completed event -> topology collapse -> progressive fill
              -> min_audit_set check -> event emission
    """

    def __init__(self):
        self.collapser = TopologyCollapser()
        self.filler = ProgressiveFillEngine()

    async def handle_node_completion(self, event: dict) -> dict:
        """Process a node completion event through the full pipeline.

        Steps:
        1. Collapse node output to Shot Card bundle structure
        2. Ensure Shot Card exists (create if first node for this shot_id)
        3. Progressive fill the target JSONB column
        4. Check min_audit_set readiness
        5. Emit events (bundle_ready, shot_card_updated)

        Returns summary dict with processing result.
        """
        shot_id = event["shot_id"]
        node_type = event["node_type"]

        # Step 1: Collapse topology
        collapse_result = self.collapser.collapse(node_type, event["node_output"])
        target_column = collapse_result["target_column"]
        merge_data = collapse_result["merge_data"]

        # Step 2: Ensure Shot Card exists
        shot_card = await self._ensure_shot_card(event)
        if shot_card is None:
            logger.error("aggregator_failed_create", shot_id=shot_id)
            return {"status": "error", "reason": "failed_to_create_shot_card"}

        # Step 3: Progressive fill
        shot_card = await self.filler.fill(shot_id, target_column, merge_data)
        if shot_card is None:
            return {"status": "error", "reason": "fill_failed"}

        # Step 4: Check readiness
        min_audit_satisfied = self.filler.check_min_audit_set(shot_card)
        bundle_complete = self.filler.check_bundle_complete(shot_card, target_column)

        # Step 5: Emit events
        await self._emit_events(
            shot_card=shot_card,
            target_column=target_column,
            bundle_complete=bundle_complete,
            min_audit_satisfied=min_audit_satisfied,
        )

        return {
            "status": "ok",
            "shot_card_id": shot_card.id,
            "shot_id": shot_id,
            "updated_column": target_column,
            "bundle_complete": bundle_complete,
            "min_audit_satisfied": min_audit_satisfied,
        }

    async def _ensure_shot_card(self, event: dict):
        """Get or create Shot Card for this shot_id.

        First node event creates the card with narrative_context
        from the event (if provided) or empty dict.
        """
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.shot_card import ShotCard

        shot_id = event["shot_id"]
        project_id = event["project_id"]

        async with async_session_factory() as session:
            result = await session.execute(
                select(ShotCard).where(ShotCard.shot_id == shot_id)
            )
            shot_card = result.scalar_one_or_none()

            if shot_card is not None:
                return shot_card

            # Create new Shot Card
            shot_card = ShotCard(
                shot_id=shot_id,
                project_id=project_id,
                narrative_context=event.get("narrative_context", {}),
                min_audit_set=["visual_bundle"],  # Default min audit set
                workflow_version=event.get("provenance", {}).get("workflow_version"),
                policy_commit_sha=event.get("provenance", {}).get("policy_commit_sha"),
                execution_id=event.get("execution_id"),
            )
            session.add(shot_card)
            await session.commit()
            await session.refresh(shot_card)

            logger.info("shot_card_created", shot_id=shot_id, project_id=project_id)
            return shot_card

    async def _emit_events(
        self, shot_card, target_column, bundle_complete, min_audit_satisfied
    ):
        """Emit progressive fill events to SSE clients."""
        # Always emit shot_card_updated
        update_event = {
            "event_type": "shot_card_updated",
            "shot_id": shot_card.shot_id,
            "project_id": shot_card.project_id,
            "shot_card_id": shot_card.id,
            "updated_fields": [target_column],
            "min_audit_set_satisfied": min_audit_satisfied,
            "audit_status": shot_card.audit_status,
        }
        await event_manager.broadcast(update_event)

        # Emit bundle_ready when a bundle becomes complete
        if bundle_complete:
            bundle_event = {
                "event_type": "bundle_ready",
                "shot_id": shot_card.shot_id,
                "project_id": shot_card.project_id,
                "bundle_type": target_column,
                "shot_card_id": shot_card.id,
            }
            await event_manager.broadcast(bundle_event)

        # Log readiness transition
        if min_audit_satisfied:
            logger.info(
                "min_audit_set_satisfied",
                shot_id=shot_card.shot_id,
                shot_card_id=shot_card.id,
                bundles_complete=target_column,
            )
```

### Pattern 5: Mock Event Ingestion API
**What:** REST endpoint for submitting mock node completion events during development
**When to use:** Testing aggregation without real OpenClaw
**Example:**
```python
# app/api/v1/shot_cards.py (endpoint for testing)
from fastapi import APIRouter, Depends
from app.services.aggregator import ShotCardAggregator
from app.core.dependencies import get_arq_pool

router = APIRouter(prefix="/api/v1/shot-cards", tags=["shot-cards"])

@router.post("/events/node-completed")
async def submit_node_completion(event: NodeCompletedEvent):
    """Submit a mock node completion event for aggregation testing.

    In production, this would be replaced by OpenClaw event bus integration.
    """
    aggregator = ShotCardAggregator()
    result = await aggregator.handle_node_completion(event.model_dump())
    return result
```

### Pattern 6: arq Background Task for Aggregation
**What:** Process node completion events as arq jobs for reliability
**When to use:** Production event processing (enqueuing from API or event listener)
**Example:**
```python
# In app/workers/tasks.py -- add to existing WorkerSettings

async def process_node_completion(ctx: dict, event_data: dict) -> dict:
    """arq task: process a node completion event through the aggregator.

    Enqueued by the event ingestion endpoint or OpenClaw webhook handler.
    Retries up to 3 times on failure.
    """
    from app.services.aggregator import ShotCardAggregator
    aggregator = ShotCardAggregator()
    return await aggregator.handle_node_completion(event_data)

# Add to WorkerSettings.functions list:
# functions = [check_timeouts, deliver_webhook, deliver_review_callback,
#              check_timeout_reminders, process_node_completion]
```

### Anti-Patterns to Avoid
- **In-place JSONB mutation without `flag_modified()`**: SQLAlchemy will NOT detect `shot_card.visual_bundle["keyframes"]["first"] = {...}` as a change. The update is silently lost on commit. ALWAYS call `flag_modified(shot_card, "visual_bundle")` after mutating, OR assign a new dict entirely.
- **Assuming node arrival order**: Video may arrive before keyframes. Audio may arrive before any visual node. The aggregator MUST be order-agnostic. Never assert that visual_bundle exists before processing audio_bundle, or vice versa.
- **Single Shot Card per project assumption**: Multiple Shot Cards exist per project (one per shot_id). Always group by shot_id, never by project_id alone.
- **Tight coupling to OpenClaw API**: Build against the event protocol (NodeCompletedEvent model), not against OpenClaw internals. This allows mock testing and future API changes without rewriting the aggregator.
- **Creating Shot Cards in the event handler without a session scope**: Each aggregation operation needs its own database session scope. Do not share sessions across events or hold sessions open across async yields.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSONB dirty tracking | Custom hash comparison to detect changes | `flag_modified(obj, col)` from SQLAlchemy | Built-in SQLAlchemy mechanism, handles all edge cases including nested mutations |
| Deep dict merging | Manual if/else for each JSONB path | Recursive `_deep_merge()` utility function | Nested structures have variable depth; recursion handles all cases uniformly |
| Event broadcasting | Direct SSE push per connection | Existing `event_manager.broadcast()` | V1 EventManager already handles per-connection queues, slow-client eviction, connection limits |
| Background task retries | Custom retry loop with sleep | arq `Retry(defer=...)` exception | arq provides exponential backoff, max tries, and job tracking out of the box |
| Node type registry | If/elif chain for each node type | Dictionary mapping `NODE_BUNDLE_MAP` | Easy to extend, data-driven, testable by inspecting the map |
| Shot Card creation race | SELECT then INSERT with try/except | PostgreSQL UNIQUE constraint on shot_id + `IntegrityError` catch | Database-level uniqueness guarantee prevents duplicate shot cards from concurrent events |

**Key insight:** The V1 codebase already provides the event broadcasting pattern (`EventManager`), the arq task pattern (`deliver_webhook`), and the database session pattern (`async_session_factory`). This phase composes these existing patterns into a new service layer. Do not reinvent event broadcasting or task queuing.

## Common Pitfalls

### Pitfall 1: JSONB Mutation Silently Lost
**What goes wrong:** Modifying a JSONB dict in-place like `shot_card.visual_bundle["keyframes"]["first"] = {...}` does NOT trigger SQLAlchemy's dirty tracking. The change is silently lost on commit.
**Why it happens:** SQLAlchemy tracks column-level assignments, not in-place mutations of mutable Python objects. JSONB is stored as a Python dict, which is mutable.
**How to avoid:** Always use one of: (1) `flag_modified(shot_card, "visual_bundle")` after mutation, (2) assign a new dict `shot_card.visual_bundle = {...merged...}`, or (3) use `MutableDict.as_mutable(JSONB)` on the column definition (but this has performance overhead for large dicts).
**Warning signs:** Data appears correct in Python debugger but is missing after page reload or API re-fetch.

### Pitfall 2: Race Condition on Shot Card Creation
**What goes wrong:** Two node completion events for the same shot_id arrive simultaneously. Both threads find no existing Shot Card, both attempt to create one. One gets a unique constraint violation.
**Why it happens:** SELECT + INSERT is not atomic without a transaction lock.
**How to avoid:** Rely on the `unique=True` constraint on `shot_id`. Wrap creation in try/except for `IntegrityError`. On duplicate, re-query the existing card. Alternatively, use PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` via SQLAlchemy's `insert().on_conflict_do_nothing()`.
**Warning signs:** Intermittent 500 errors on concurrent node completions for the same shot.

### Pitfall 3: Out-of-Order Completion Causes Data Loss
**What goes wrong:** Video clip arrives before keyframes. The code assumes keyframes exist and tries to read `visual_bundle["keyframes"]["first"]` -- gets KeyError or None.
**Why it happens:** Pipeline nodes execute in parallel. The topology collapser must handle any node arriving at any time.
**How to avoid:** Always use the deep merge pattern -- merge new data INTO existing (possibly empty) dict. Never assume any field already exists. Use `dict.get()` and `or {}` defaults.
**Warning signs:** Aggregation fails with KeyError on specific event orderings.

### Pitfall 4: min_audit_set Check Returns False Positives
**What goes wrong:** min_audit_set check passes because visual_bundle has any data (e.g., only the prompt), but the keyframes are still missing. Review is unlocked prematurely.
**Why it happens:** Checking `bool(bundle)` only verifies the column is non-null, not that it contains the minimum required fields.
**How to avoid:** `check_min_audit_set` must verify specific required sub-fields exist within each bundle, not just that the bundle is non-null. For visual_bundle, verify `keyframes.first` exists. For audio_bundle, verify `status != "pending"`.
**Warning signs:** Review UI shows a Shot Card with missing keyframes or broken video player.

### Pitfall 5: Event Flooding on Rapid Node Completions
**What goes wrong:** A pipeline with 10 nodes for the same shot fires 10 `shot_card_updated` events in rapid succession (within 100ms). Each triggers an SSE broadcast and potentially a database query in subscribers.
**Why it happens:** No debouncing or batching in the event emission path.
**How to avoid:** For the initial implementation, this is acceptable -- SSE broadcasts are cheap (asyncio.Queue.put_nowait). If it becomes a problem, add debouncing (e.g., emit at most once per 200ms per shot_id using a short TTL in Redis). But do not over-engineer this upfront.
**Warning signs:** SSE client receives many rapid updates for the same shot card; UI flickers.

### Pitfall 6: arq Task Serialization of Pydantic Models
**What goes wrong:** Enqueuing a Pydantic model directly as an arq job argument fails because arq serializes to JSON and Pydantic models are not JSON-serializable by default.
**Why it happens:** arq uses `msgpack` or JSON serialization for job arguments.
**How to avoid:** Always call `event.model_dump()` before enqueuing as an arq job. Use dict, not Pydantic model instances, as job arguments.
**Warning signs:** `TypeError: Object of type NodeCompletedEvent is not JSON serializable` when enqueuing arq jobs.

## Code Examples

### Server-Side JSONB Partial Update (Alternative to ORM-level)
```python
# Source: PostgreSQL jsonb_set + SQLAlchemy expression language
# Use when you want to avoid loading the full row (performance optimization)
from sqlalchemy import update, func, cast, text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import async_session_factory
from app.models.shot_card import ShotCard

async def server_side_jsonb_merge(shot_id: str, column: str, path: str, value: dict):
    """Update a JSONB field server-side without loading the row.

    Note: For nested path updates, this is more complex. Recommended
    for simple top-level key merges only. For deep merges, the ORM-level
    approach (load + deep_merge + flag_modified) is simpler and sufficient.
    """
    async with async_session_factory() as session:
        # This works for top-level keys in the JSONB column
        stmt = (
            update(ShotCard)
            .where(ShotCard.shot_id == shot_id)
            .values(
                **{column: func.jsonb_set(
                    getattr(ShotCard, column),
                    cast(path, JSONB),  # e.g. '{keyframes}'
                    cast(value, JSONB),
                    True,  # create_if_missing
                )}
            )
        )
        await session.execute(stmt)
        await session.commit()
```

### Shot Card CRUD API Endpoints
```python
# app/api/v1/shot_cards.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.shot_card import ShotCard
from app.models.schemas import (
    ShotCardCreate, ShotCardResponse, ApiResponse, PaginatedResponse,
    NodeCompletedEvent,  # For mock event ingestion
)

router = APIRouter(prefix="/api/v1/shot-cards", tags=["shot-cards"])

@router.get("", response_model=PaginatedResponse[ShotCardResponse])
async def list_shot_cards(
    project_id: str | None = Query(None),
    audit_status: str | None = Query(None),
    cursor: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List Shot Cards with optional filtering and cursor pagination."""
    query = select(ShotCard)
    if project_id:
        query = query.where(ShotCard.project_id == project_id)
    if audit_status:
        query = query.where(ShotCard.audit_status == audit_status)
    query = query.where(ShotCard.id > cursor).order_by(ShotCard.id).limit(limit + 1)
    result = await db.execute(query)
    items = result.scalars().all()
    has_more = len(items) > limit
    items = items[:limit]
    return PaginatedResponse(
        items=[ShotCardResponse.model_validate(i) for i in items],
        next_cursor=items[-1].id if items and has_more else None,
        has_more=has_more,
    )

@router.get("/{shot_card_id}", response_model=ApiResponse[ShotCardResponse])
async def get_shot_card(shot_card_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single Shot Card by ID."""
    shot_card = await db.get(ShotCard, shot_card_id)
    if not shot_card:
        raise HTTPException(404, "Shot Card not found")
    return ApiResponse(data=ShotCardResponse.model_validate(shot_card))

@router.get("/by-shot/{shot_id}", response_model=ApiResponse[ShotCardResponse])
async def get_shot_card_by_shot_id(shot_id: str, db: AsyncSession = Depends(get_db)):
    """Get a Shot Card by its shot_id (natural key)."""
    result = await db.execute(
        select(ShotCard).where(ShotCard.shot_id == shot_id)
    )
    shot_card = result.scalar_one_or_none()
    if not shot_card:
        raise HTTPException(404, f"Shot Card with shot_id={shot_id} not found")
    return ApiResponse(data=ShotCardResponse.model_validate(shot_card))
```

### Handling IntegrityError on Concurrent Creation
```python
# Pattern for safe Shot Card creation under concurrency
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from app.core.database import async_session_factory
from app.models.shot_card import ShotCard

async def get_or_create_shot_card(event: dict) -> ShotCard:
    """Get existing or create new Shot Card, handling concurrent creation."""
    shot_id = event["shot_id"]

    async with async_session_factory() as session:
        # Try to get existing
        result = await session.execute(
            select(ShotCard).where(ShotCard.shot_id == shot_id)
        )
        shot_card = result.scalar_one_or_none()
        if shot_card:
            return shot_card

        # Try to create
        shot_card = ShotCard(
            shot_id=shot_id,
            project_id=event["project_id"],
            narrative_context=event.get("narrative_context", {}),
            min_audit_set=["visual_bundle"],
            execution_id=event.get("execution_id"),
        )
        session.add(shot_card)

        try:
            await session.commit()
            await session.refresh(shot_card)
            return shot_card
        except IntegrityError:
            # Another concurrent event created it first -- re-query
            await session.rollback()
            result = await session.execute(
                select(ShotCard).where(ShotCard.shot_id == shot_id)
            )
            return result.scalar_one()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single Review submission (atomic) | Progressive aggregation from multiple node events | V2 Phase 16 | Review data arrives in pieces, not all at once |
| Fixed Review fields (type, content_ref) | JSONB bundles with flexible structure | V2 Phase 15-16 | Schema is template-driven, not hardcoded |
| Direct API submission only | Event-driven + arq background processing | V2 Phase 16 | Decoupled ingestion from processing |
| In-process event broadcast | Redis pub/sub for cross-process events | V2 Phase 16 | arq worker can publish events that API process SSE clients receive |

**Deprecated/outdated:**
- V1 Review submission (POST /api/v1/reviews with flat data): Replaced by event-driven aggregation. Shot Cards are assembled from multiple node events, not submitted as a single blob.
- V1 Review states (PENDING/POLICY_EVAL/APPROVING/COMPLETE): Shot Card uses different statuses (awaiting_audit/approved/rejected/pending_audio). The old state machine does not apply.

## Open Questions

1. **Redis pub/sub vs in-process event broadcasting**
   - What we know: V1 EventManager uses in-process asyncio.Queue broadcast. arq workers run in the same event loop as FastAPI (per CLAUDE.md). SSE clients connect to the API process.
   - What's unclear: Whether arq workers will always share the same process as the API server, or may run as a separate process in the future.
   - Recommendation: Use the existing in-process `event_manager.broadcast()` for now. If arq workers are ever separated into their own process, add Redis pub/sub as a bridge. Do not add Redis pub/sub complexity upfront.

2. **Node type extensibility mechanism**
   - What we know: The initial NODE_BUNDLE_MAP is hardcoded. New node types will be added as the pipeline evolves.
   - What's unclear: Whether node type mapping should come from Git-managed YAML templates (per V2 architecture) or stay hardcoded.
   - Recommendation: Start with hardcoded dict. The Phase 17 GitOps layer will introduce template-driven mapping. The dict is easily migrated to a YAML-loaded registry later.

3. **Candidate array handling in topology collapser**
   - What we know: The VisualBundle model has a `candidates: list[Candidate]` field for multi-draw results. Multiple nodes may produce candidates for the same shot.
   - What's unclear: How candidates are identified and appended. Each candidate has a `candidate_id` -- do we append to the list or replace by candidate_id?
   - Recommendation: Append by default. If a duplicate `candidate_id` is found, replace that candidate in the list. Handle this in the deep_merge logic for list fields.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Shot Card storage | Container | timescale/timescaledb:latest-pg16 | -- |
| Redis | Event pub/sub, arq queue | Container | redis:7-alpine | -- |
| Python 3.12 | Runtime | Yes | 3.12.3 | -- |
| SQLAlchemy 2.0 | ORM + JSONB | Yes | 2.0.49 | -- |
| arq 0.28.0 | Background tasks | Yes | 0.28.0 | -- |
| Pydantic 2.13 | Event validation | Yes | 2.13.3 | -- |
| redis-py 5.3 | Redis client | Yes | 5.3.1 | -- |
| Docker | Container runtime | Yes | 29.4.3 | -- |

**Missing dependencies with no fallback:**
- None. All dependencies are already installed or containerized from Phase 15.

**Missing dependencies with fallback:**
- None.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `app/models/shot_card.py` -- Shot Card SQLAlchemy model with JSONB columns (authoritative field definitions)
- Existing codebase: `app/core/events.py` -- EventManager with asyncio.Queue SSE broadcast pattern (authoritative event mechanism)
- Existing codebase: `app/workers/tasks.py` -- arq task pattern with Retry and WorkerSettings (authoritative task queue pattern)
- `.planning/research/V2-ARCHITECTURE.md` -- Shot Card aggregator design, topology collapser, progressive fill (authoritative V2 design)
- `.planning/research/V2-GAP-ANALYSIS.md` -- GAP-2.2, GAP-2.9 gap definitions (authoritative gap scope)
- SQLAlchemy 2.0 docs: `flag_modified()` for JSONB mutation detection (verified via `python3 -c` import check)

### Secondary (MEDIUM confidence)
- PostgreSQL `jsonb_set()` documentation -- server-side partial JSONB updates (web search verified)
- arq 0.28 API patterns -- enqueue_job, Retry exception, WorkerSettings (existing codebase patterns verified)

### Tertiary (LOW confidence)
- Redis pub/sub for cross-process event distribution -- recommended pattern but not yet needed (in-process broadcast sufficient for current architecture)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all dependencies already installed and verified, no new packages needed
- Architecture: HIGH -- pattern is well-defined in V2 architecture spec, existing codebase provides clear integration patterns
- Pitfalls: HIGH -- JSONB mutation detection, race conditions, and out-of-order handling are well-understood SQLAlchemy/async patterns
- Event protocol: HIGH -- event types specified in CONTEXT.md, Pydantic models provide strong typing

**Research date:** 2026-05-16
**Valid until:** 2026-06-16 (stable -- no new dependencies, patterns are well-established)
