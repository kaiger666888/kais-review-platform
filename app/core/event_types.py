"""Typed event protocol for Shot Card aggregation pipeline.

Defines Pydantic models for all events flowing through the aggregation
system: node completion, bundle readiness, and shot card updates.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NodeCompletedEvent(BaseModel):
    """OpenClaw node completion event.

    Emitted when a pipeline node (FLUX.1-dev, Wan2.2-T2V, AudioPrompt, etc.)
    finishes execution and produces output for a shot.
    """

    event_type: Literal["node_completed"] = "node_completed"
    execution_id: str
    shot_id: str
    project_id: str
    node_type: str  # e.g. "FLUX.1-dev", "Wan2.2-T2V", "AudioPrompt"
    node_output: dict  # The actual output data (URLs, metadata)
    narrative_context: dict | None = None  # Populated by first node in shot
    provenance: dict | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class BundleReadyEvent(BaseModel):
    """Fired when a bundle (visual/audio) becomes complete.

    A bundle is complete when all required fields are populated:
    - visual_bundle: keyframes (first) + prompt
    - audio_bundle: (bgm_prompt or sfx_prompt) + status != pending
    """

    event_type: Literal["bundle_ready"] = "bundle_ready"
    shot_id: str
    project_id: str
    bundle_type: Literal["visual_bundle", "audio_bundle"]
    shot_card_id: int


class ShotCardUpdatedEvent(BaseModel):
    """Fired when any Shot Card JSONB field changes.

    Emitted after every progressive fill operation, regardless of whether
    the bundle is complete or the min_audit_set is satisfied.
    """

    event_type: Literal["shot_card_updated"] = "shot_card_updated"
    shot_id: str
    project_id: str
    shot_card_id: int
    updated_fields: list[str]  # Which JSONB fields changed
    min_audit_set_satisfied: bool
    audit_status: str
