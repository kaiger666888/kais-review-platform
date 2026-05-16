"""Checkpoint types for serializing pipeline execution state.

Provides Pydantic models for capturing OpenClaw execution state as
RunStateSnapshots and producing ResumeCommands after approval.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RunStateSnapshot(BaseModel):
    """Serialized execution state of a ShotCard at the point it enters review.

    Captures all data needed to resume the OpenClaw pipeline after approval.
    Stored in Redis hash at key ``checkpoint:{shot_id}``.
    """

    shot_id: str
    execution_id: str
    project_id: str
    narrative_context: dict = Field(default_factory=dict)
    visual_bundle_state: dict = Field(default_factory=dict)
    audio_bundle_state: dict = Field(default_factory=dict)
    routing_decision: str
    created_at: datetime


class ResumeCommand(BaseModel):
    """Command produced after approval to resume pipeline execution.

    Contains the full snapshot plus approval metadata. Stored in Redis
    string at key ``resume:{execution_id}`` with 1-hour TTL.
    """

    shot_id: str
    execution_id: str
    project_id: str
    approved_at: datetime
    approved_by: str
    snapshot: RunStateSnapshot
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ShotCardApprovedEvent(BaseModel):
    """Event emitted when a ShotCard is approved and ResumeCommand created."""

    shot_id: str
    project_id: str
    outlet: str
    actor: str
    timestamp: datetime
    resume_command_id: str


class ShotCardRejectedEvent(BaseModel):
    """Event emitted when a ShotCard is rejected."""

    shot_id: str
    project_id: str
    outlet: str
    actor: str
    reason: str | None = None
    timestamp: datetime
