"""Checkpoint Manager: serialize pipeline state to Redis and produce ResumeCommands.

Captures ShotCard execution state as RunStateSnapshots in Redis hashes.
After approval, creates ResumeCommands with all data needed for pipeline
resume. Handles TTL per route type and checkpoint cleanup.
"""

import json
from datetime import datetime, timezone

import structlog

from app.core.checkpoint_types import (
    ResumeCommand,
    RunStateSnapshot,
    ShotCardApprovedEvent,
    ShotCardRejectedEvent,
)

logger = structlog.get_logger(__name__)

# TTL configuration (seconds) per routing decision
_TTL_SECONDS: dict[str, int] = {
    "HUMAN": 86400,  # 24 hours
    "AI_AUDIT": 300,  # 5 minutes
    "AUTO": 0,  # No TTL needed (immediate cleanup)
    "BLOCK": 0,  # No TTL needed (immediate cleanup)
}


class CheckpointManager:
    """Manages RunState snapshots and ResumeCommands in Redis.

    Checkpoints are stored as Redis hashes at ``checkpoint:{shot_id}``.
    ResumeCommands are stored as JSON strings at ``resume:{execution_id}``
    with a 1-hour TTL.
    """

    def __init__(self, redis, event_manager=None, settings=None):
        """Initialize CheckpointManager.

        Args:
            redis: Async Redis client instance.
            event_manager: Optional EventManager for broadcasting events.
            settings: Optional Settings instance for timeout configuration.
        """
        self._redis = redis
        self._event_manager = event_manager
        self._settings = settings

    def _get_ttl(self, routing_decision: str) -> int:
        """Get TTL in seconds for a given routing decision.

        Falls back to settings if available, otherwise uses defaults.
        """
        if routing_decision in ("AUTO", "BLOCK"):
            return 0

        if self._settings:
            if routing_decision == "HUMAN":
                return self._settings.review_timeout_minutes * 60
            if routing_decision == "AI_AUDIT":
                return self._settings.ai_audit_timeout_minutes * 60

        return _TTL_SECONDS.get(routing_decision, 86400)

    async def save_snapshot(self, shot_card) -> RunStateSnapshot:
        """Serialize ShotCard state to a Redis hash.

        Stores execution_id, project_id, narrative_context, visual/audio
        bundle state, routing_decision, and created_at in the hash
        ``checkpoint:{shot_id}``.

        Args:
            shot_card: ShotCard ORM object with all required fields.

        Returns:
            RunStateSnapshot with the serialized state.
        """
        snapshot = RunStateSnapshot(
            shot_id=shot_card.shot_id,
            execution_id=shot_card.execution_id or "",
            project_id=shot_card.project_id,
            narrative_context=shot_card.narrative_context or {},
            visual_bundle_state=shot_card.visual_bundle or {},
            audio_bundle_state=shot_card.audio_bundle or {},
            routing_decision=shot_card.routing_decision or "HUMAN",
            created_at=shot_card.created_at
            if shot_card.created_at
            else datetime.now(timezone.utc),
        )

        key = f"checkpoint:{snapshot.shot_id}"
        mapping = {
            "execution_id": snapshot.execution_id,
            "shot_id": snapshot.shot_id,
            "project_id": snapshot.project_id,
            "routing_decision": snapshot.routing_decision,
            "narrative_context": json.dumps(snapshot.narrative_context),
            "visual_bundle": json.dumps(snapshot.visual_bundle_state),
            "audio_bundle": json.dumps(snapshot.audio_bundle_state),
            "created_at": snapshot.created_at.isoformat(),
        }

        await self._redis.hset(key, mapping=mapping)

        ttl = self._get_ttl(snapshot.routing_decision)
        if ttl > 0:
            await self._redis.expire(key, ttl)

        logger.info(
            "checkpoint_saved",
            shot_id=snapshot.shot_id,
            routing_decision=snapshot.routing_decision,
            ttl=ttl,
        )

        return snapshot

    async def load_snapshot(self, shot_id: str) -> RunStateSnapshot | None:
        """Load a RunStateSnapshot from Redis.

        Args:
            shot_id: The shot ID to load the checkpoint for.

        Returns:
            RunStateSnapshot if found, None if the key does not exist.
        """
        key = f"checkpoint:{shot_id}"
        data = await self._redis.hgetall(key)

        if not data:
            return None

        # Redis returns bytes; decode keys and values
        decoded = {}
        for k, v in data.items():
            key_str = k.decode() if isinstance(k, bytes) else k
            val_str = v.decode() if isinstance(v, bytes) else v
            decoded[key_str] = val_str

        return RunStateSnapshot(
            shot_id=decoded["shot_id"],
            execution_id=decoded["execution_id"],
            project_id=decoded["project_id"],
            narrative_context=json.loads(decoded["narrative_context"]),
            visual_bundle_state=json.loads(decoded["visual_bundle"]),
            audio_bundle_state=json.loads(decoded["audio_bundle"]),
            routing_decision=decoded["routing_decision"],
            created_at=datetime.fromisoformat(decoded["created_at"]),
        )

    async def create_resume_command(
        self, shot_id: str, actor: str
    ) -> ResumeCommand | None:
        """Create a ResumeCommand after approval.

        Loads the snapshot, creates a ResumeCommand with approval metadata,
        and stores it in Redis at ``resume:{execution_id}`` with 1-hour TTL.

        Args:
            shot_id: The shot ID to create a resume command for.
            actor: Who approved the shot (e.g. "reviewer", "auto-router").

        Returns:
            ResumeCommand if snapshot exists, None otherwise.
        """
        snapshot = await self.load_snapshot(shot_id)
        if snapshot is None:
            return None

        now = datetime.now(timezone.utc)
        cmd = ResumeCommand(
            shot_id=snapshot.shot_id,
            execution_id=snapshot.execution_id,
            project_id=snapshot.project_id,
            approved_at=now,
            approved_by=actor,
            snapshot=snapshot,
        )

        resume_key = f"resume:{snapshot.execution_id}"
        await self._redis.set(resume_key, cmd.model_dump_json(), ex=3600)

        # Emit approved event if event manager is available
        if self._event_manager:
            event = ShotCardApprovedEvent(
                shot_id=snapshot.shot_id,
                project_id=snapshot.project_id,
                outlet=snapshot.routing_decision,
                actor=actor,
                timestamp=now,
                resume_command_id=cmd.command_id,
            )
            await self._event_manager.broadcast(event.model_dump())

        logger.info(
            "resume_command_created",
            shot_id=snapshot.shot_id,
            execution_id=snapshot.execution_id,
            actor=actor,
        )

        return cmd

    async def clear_checkpoint(self, shot_id: str) -> None:
        """Remove checkpoint and associated resume keys from Redis.

        Looks up the execution_id from the checkpoint hash and deletes
        both the checkpoint and resume keys.

        Args:
            shot_id: The shot ID to clear the checkpoint for.
        """
        checkpoint_key = f"checkpoint:{shot_id}"

        # Try to get execution_id for resume key cleanup
        data = await self._redis.hgetall(checkpoint_key)
        if data:
            exec_id_bytes = data.get(b"execution_id", data.get("execution_id"))
            if exec_id_bytes:
                exec_id = (
                    exec_id_bytes.decode()
                    if isinstance(exec_id_bytes, bytes)
                    else exec_id_bytes
                )
                resume_key = f"resume:{exec_id}"
                await self._redis.delete(resume_key)

        await self._redis.delete(checkpoint_key)

        logger.info("checkpoint_cleared", shot_id=shot_id)

    async def on_approval(
        self, shot_id: str, actor: str
    ) -> ResumeCommand | None:
        """Convenience method: approve a shot card checkpoint.

        Loads snapshot, creates resume command, then clears checkpoint.
        Called by the router after approval.

        Args:
            shot_id: The shot ID to approve.
            actor: Who approved the shot.

        Returns:
            ResumeCommand if snapshot exists, None otherwise.
        """
        cmd = await self.create_resume_command(shot_id, actor)
        if cmd:
            await self.clear_checkpoint(shot_id)
        return cmd

    async def on_rejection(
        self, shot_id: str, actor: str, reason: str | None = None
    ) -> None:
        """Handle rejection: clear checkpoint and emit rejection event.

        Args:
            shot_id: The shot ID that was rejected.
            actor: Who rejected the shot.
            reason: Optional rejection reason.
        """
        # Get snapshot data for event before clearing
        snapshot = await self.load_snapshot(shot_id)

        await self.clear_checkpoint(shot_id)

        # Emit rejected event if event manager is available
        if self._event_manager and snapshot:
            event = ShotCardRejectedEvent(
                shot_id=snapshot.shot_id,
                project_id=snapshot.project_id,
                outlet=snapshot.routing_decision,
                actor=actor,
                reason=reason,
                timestamp=datetime.now(timezone.utc),
            )
            await self._event_manager.broadcast(event.model_dump())

        logger.info(
            "checkpoint_rejected",
            shot_id=shot_id,
            actor=actor,
            reason=reason,
        )
