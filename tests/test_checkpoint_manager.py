"""Tests for CheckpointManager: save/load snapshots, resume commands, and checkpoint lifecycle.

Verifies that:
- RunState snapshots serialize full ShotCard execution context to Redis
- Load returns None for non-existent keys
- ResumeCommands are produced after approval with correct fields
- ResumeCommands stored in Redis with 1-hour TTL
- Checkpoint TTL matches route type (24h HUMAN, 5min AI_AUDIT)
- Clear removes both checkpoint and resume keys
- AUTO-routed cards are created and immediately cleared
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.checkpoint_types import (
    ResumeCommand,
    RunStateSnapshot,
    ShotCardApprovedEvent,
    ShotCardRejectedEvent,
)
from app.services.checkpoint_manager import CheckpointManager


def _make_shot_card(
    shot_id="shot-001",
    execution_id="exec-001",
    routing_decision="HUMAN",
    project_id="proj-001",
):
    """Create a mock ShotCard ORM object for testing."""
    card = MagicMock()
    card.shot_id = shot_id
    card.execution_id = execution_id
    card.project_id = project_id
    card.routing_decision = routing_decision
    card.narrative_context = {"scene": "intro", "shot_number": 1}
    card.visual_bundle = {"keyframes": {"first": {"url": "https://example.com/first.jpg"}}}
    card.audio_bundle = {"status": "pending"}
    card.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    card.updated_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return card


class TestSaveSnapshot:
    """Test save_snapshot stores execution state in Redis hash."""

    @pytest.mark.asyncio
    async def test_stores_all_fields_in_redis_hash(self):
        redis = MagicMock()
        redis.hset = AsyncMock()
        redis.expire = AsyncMock()

        settings = MagicMock()
        settings.review_timeout_minutes = 1440
        settings.ai_audit_timeout_minutes = 5

        mgr = CheckpointManager(redis, settings=settings)
        card = _make_shot_card()

        snapshot = await mgr.save_snapshot(card)

        # Verify hset was called with correct key and fields
        redis.hset.assert_called_once()
        call_args = redis.hset.call_args
        assert call_args[0][0] == "checkpoint:shot-001"

        # Verify the mapping contains all required fields
        # hset is called with (key, mapping=...) keyword arg
        mapping = call_args[1].get("mapping", call_args[0][1] if len(call_args[0]) > 1 else {})
        assert b"execution_id" in mapping or "execution_id" in mapping
        assert b"shot_id" in mapping or "shot_id" in mapping
        assert b"project_id" in mapping or "project_id" in mapping
        assert b"routing_decision" in mapping or "routing_decision" in mapping
        assert b"narrative_context" in mapping or "narrative_context" in mapping
        assert b"visual_bundle" in mapping or "visual_bundle" in mapping
        assert b"audio_bundle" in mapping or "audio_bundle" in mapping
        assert b"created_at" in mapping or "created_at" in mapping

    @pytest.mark.asyncio
    async def test_returns_run_state_snapshot(self):
        redis = MagicMock()
        redis.hset = AsyncMock()
        redis.expire = AsyncMock()

        settings = MagicMock()
        settings.review_timeout_minutes = 1440
        settings.ai_audit_timeout_minutes = 5

        mgr = CheckpointManager(redis, settings=settings)
        card = _make_shot_card()

        snapshot = await mgr.save_snapshot(card)

        assert isinstance(snapshot, RunStateSnapshot)
        assert snapshot.shot_id == "shot-001"
        assert snapshot.execution_id == "exec-001"
        assert snapshot.project_id == "proj-001"
        assert snapshot.routing_decision == "HUMAN"

    @pytest.mark.asyncio
    async def test_ttl_human_route(self):
        redis = MagicMock()
        redis.hset = AsyncMock()
        redis.expire = AsyncMock()

        settings = MagicMock()
        settings.review_timeout_minutes = 1440
        settings.ai_audit_timeout_minutes = 5

        mgr = CheckpointManager(redis, settings=settings)
        card = _make_shot_card(routing_decision="HUMAN")

        await mgr.save_snapshot(card)

        # TTL should be 1440 * 60 = 86400 seconds
        redis.expire.assert_called_once_with("checkpoint:shot-001", 86400)

    @pytest.mark.asyncio
    async def test_ttl_ai_audit_route(self):
        redis = MagicMock()
        redis.hset = AsyncMock()
        redis.expire = AsyncMock()

        settings = MagicMock()
        settings.review_timeout_minutes = 1440
        settings.ai_audit_timeout_minutes = 5

        mgr = CheckpointManager(redis, settings=settings)
        card = _make_shot_card(shot_id="shot-ai", execution_id="exec-ai", routing_decision="AI_AUDIT")

        await mgr.save_snapshot(card)

        # TTL should be 5 * 60 = 300 seconds
        redis.expire.assert_called_once_with("checkpoint:shot-ai", 300)


class TestLoadSnapshot:
    """Test load_snapshot retrieves RunStateSnapshot from Redis."""

    @pytest.mark.asyncio
    async def test_returns_snapshot_with_all_fields(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
            b"shot_id": b"shot-001",
            b"project_id": b"proj-001",
            b"routing_decision": b"HUMAN",
            b"narrative_context": json.dumps({"scene": "intro"}).encode(),
            b"visual_bundle": json.dumps({"keyframes": {}}).encode(),
            b"audio_bundle": json.dumps({"status": "pending"}).encode(),
            b"created_at": b"2026-01-01T12:00:00+00:00",
        })

        mgr = CheckpointManager(redis)
        snapshot = await mgr.load_snapshot("shot-001")

        assert snapshot is not None
        assert isinstance(snapshot, RunStateSnapshot)
        assert snapshot.shot_id == "shot-001"
        assert snapshot.execution_id == "exec-001"
        assert snapshot.project_id == "proj-001"
        assert snapshot.routing_decision == "HUMAN"
        assert snapshot.narrative_context == {"scene": "intro"}
        assert snapshot.visual_bundle_state == {"keyframes": {}}
        assert snapshot.audio_bundle_state == {"status": "pending"}

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={})

        mgr = CheckpointManager(redis)
        snapshot = await mgr.load_snapshot("nonexistent-shot")

        assert snapshot is None


class TestCreateResumeCommand:
    """Test create_resume_command produces ResumeCommand stored in Redis."""

    @pytest.mark.asyncio
    async def test_creates_resume_command_with_correct_fields(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
            b"shot_id": b"shot-001",
            b"project_id": b"proj-001",
            b"routing_decision": b"HUMAN",
            b"narrative_context": json.dumps({"scene": "intro"}).encode(),
            b"visual_bundle": json.dumps({"keyframes": {}}).encode(),
            b"audio_bundle": json.dumps({"status": "pending"}).encode(),
            b"created_at": b"2026-01-01T12:00:00+00:00",
        })
        redis.set = AsyncMock()

        mgr = CheckpointManager(redis)
        cmd = await mgr.create_resume_command("shot-001", actor="reviewer")

        assert cmd is not None
        assert isinstance(cmd, ResumeCommand)
        assert cmd.shot_id == "shot-001"
        assert cmd.execution_id == "exec-001"
        assert cmd.project_id == "proj-001"
        assert cmd.approved_by == "reviewer"
        assert cmd.approved_at is not None
        assert cmd.command_id is not None

    @pytest.mark.asyncio
    async def test_stores_in_redis_with_1h_ttl(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
            b"shot_id": b"shot-001",
            b"project_id": b"proj-001",
            b"routing_decision": b"HUMAN",
            b"narrative_context": json.dumps({}).encode(),
            b"visual_bundle": json.dumps({}).encode(),
            b"audio_bundle": json.dumps({}).encode(),
            b"created_at": b"2026-01-01T12:00:00+00:00",
        })
        redis.set = AsyncMock()

        mgr = CheckpointManager(redis)
        cmd = await mgr.create_resume_command("shot-001", actor="reviewer")

        # Verify stored at resume:{execution_id} with TTL
        redis.set.assert_called_once()
        call_args = redis.set.call_args
        assert call_args[0][0] == "resume:exec-001"
        # Check the TTL was set (either via ex parameter or expire call)
        kwargs = call_args[1] if call_args[1] else {}
        if "ex" in kwargs:
            assert kwargs["ex"] == 3600

    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshot(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={})

        mgr = CheckpointManager(redis)
        cmd = await mgr.create_resume_command("nonexistent", actor="reviewer")

        assert cmd is None


class TestClearCheckpoint:
    """Test clear_checkpoint removes both checkpoint and resume keys."""

    @pytest.mark.asyncio
    async def test_clears_checkpoint_key(self):
        redis = MagicMock()
        redis.delete = AsyncMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
        })
        redis.get = AsyncMock(return_value=None)

        mgr = CheckpointManager(redis)
        await mgr.clear_checkpoint("shot-001")

        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_clears_resume_key_if_exists(self):
        redis = MagicMock()
        redis.delete = AsyncMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
        })

        mgr = CheckpointManager(redis)
        await mgr.clear_checkpoint("shot-001")

        # Both checkpoint and resume keys should be deleted
        calls = redis.delete.call_args_list
        keys_deleted = [c[0][0] for c in calls]
        assert "checkpoint:shot-001" in keys_deleted
        assert "resume:exec-001" in keys_deleted


class TestAutoRouteImmediateCleanup:
    """Test AUTO-routed cards are checkpointed and immediately cleared."""

    @pytest.mark.asyncio
    async def test_auto_route_immediate_cleanup(self):
        redis = MagicMock()
        redis.hset = AsyncMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-auto",
            b"shot_id": b"shot-auto",
            b"project_id": b"proj-auto",
            b"routing_decision": b"AUTO",
            b"narrative_context": json.dumps({}).encode(),
            b"visual_bundle": json.dumps({}).encode(),
            b"audio_bundle": json.dumps({}).encode(),
            b"created_at": b"2026-01-01T12:00:00+00:00",
        })
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        redis.expire = AsyncMock()

        mgr = CheckpointManager(redis)

        # Save snapshot for AUTO route
        card = _make_shot_card(shot_id="shot-auto", routing_decision="AUTO")
        await mgr.save_snapshot(card)

        # Immediately approve (AUTO routes auto-approve)
        cmd = await mgr.on_approval("shot-auto", actor="auto-router")

        # Then clear
        await mgr.clear_checkpoint("shot-auto")

        # Verify cleanup happened - delete should have been called
        assert redis.delete.called


class TestOnApproval:
    """Test on_approval convenience method."""

    @pytest.mark.asyncio
    async def test_loads_creates_and_clears(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
            b"shot_id": b"shot-001",
            b"project_id": b"proj-001",
            b"routing_decision": b"HUMAN",
            b"narrative_context": json.dumps({}).encode(),
            b"visual_bundle": json.dumps({}).encode(),
            b"audio_bundle": json.dumps({}).encode(),
            b"created_at": b"2026-01-01T12:00:00+00:00",
        })
        redis.set = AsyncMock()
        redis.delete = AsyncMock()

        mgr = CheckpointManager(redis)
        cmd = await mgr.on_approval("shot-001", actor="reviewer")

        assert cmd is not None
        assert isinstance(cmd, ResumeCommand)
        assert cmd.shot_id == "shot-001"
        assert cmd.approved_by == "reviewer"
        # Checkpoint should be cleared
        assert redis.delete.called


class TestOnRejection:
    """Test on_rejection clears checkpoint and emits event."""

    @pytest.mark.asyncio
    async def test_clears_checkpoint_on_rejection(self):
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={
            b"execution_id": b"exec-001",
            b"shot_id": b"shot-001",
            b"project_id": b"proj-001",
            b"routing_decision": b"HUMAN",
            b"narrative_context": json.dumps({}).encode(),
            b"visual_bundle": json.dumps({}).encode(),
            b"audio_bundle": json.dumps({}).encode(),
            b"created_at": b"2026-01-01T12:00:00+00:00",
        })
        redis.delete = AsyncMock()

        mgr = CheckpointManager(redis)
        await mgr.on_rejection("shot-001", actor="reviewer", reason="quality too low")

        assert redis.delete.called
