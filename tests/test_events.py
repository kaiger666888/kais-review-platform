"""Tests for EventManager and emit_state_change event pipeline.

Tests the SSE event broadcasting, connection management, slow client
dropping, and the emit_state_change integration function that wires
state machine transitions into the SSE + webhook delivery pipeline.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.core.events import EventManager, emit_state_change, event_manager


class TestEventManagerCreateConnection:
    """Test EventManager.create_connection()."""

    def test_create_connection_adds_to_connections(self):
        manager = EventManager()
        queue = manager.create_connection()
        assert queue in manager._connections
        assert manager.connection_count == 1

    def test_create_connection_returns_queue_with_maxsize(self):
        manager = EventManager()
        queue = manager.create_connection()
        assert isinstance(queue, asyncio.Queue)
        assert queue.maxsize == 100


class TestEventManagerRemoveConnection:
    """Test EventManager.remove_connection()."""

    def test_remove_connection_removes_from_set(self):
        manager = EventManager()
        queue = manager.create_connection()
        manager.remove_connection(queue)
        assert queue not in manager._connections
        assert manager.connection_count == 0

    def test_remove_nonexistent_connection_no_error(self):
        """Removing a queue that was never added should not raise."""
        manager = EventManager()
        other_queue = asyncio.Queue()
        manager.remove_connection(other_queue)  # Should not raise
        assert manager.connection_count == 0


class TestEventManagerBroadcast:
    """Test EventManager.broadcast()."""

    @pytest.mark.asyncio
    async def test_broadcast_to_two_connections(self):
        manager = EventManager()
        q1 = manager.create_connection()
        q2 = manager.create_connection()

        event = {"review_id": 1, "old_state": "PENDING", "new_state": "POLICY_EVAL"}
        await manager.broadcast(event)

        data1 = q1.get_nowait()
        data2 = q2.get_nowait()
        assert data1 == event
        assert data2 == event

    @pytest.mark.asyncio
    async def test_broadcast_drops_slow_client(self):
        """Client with full queue is removed on broadcast."""
        manager = EventManager()
        slow_q = asyncio.Queue(maxsize=1)
        manager._connections.add(slow_q)
        slow_q.put_nowait("old_data")  # Fill the queue

        fast_q = manager.create_connection()

        event = {"review_id": 2, "new_state": "COMPLETE"}
        await manager.broadcast(event)

        # Slow client should be removed
        assert slow_q not in manager._connections
        # Fast client should still receive
        assert fast_q.get_nowait() == event
        assert manager.connection_count == 1


class TestEventManagerConnectionCount:
    """Test EventManager.connection_count property."""

    def test_connection_count_tracks_additions(self):
        manager = EventManager()
        manager.create_connection()
        manager.create_connection()
        manager.create_connection()
        assert manager.connection_count == 3

    def test_connection_count_50_plus(self):
        """Verify no hard limit -- just logging at 50+."""
        manager = EventManager()
        queues = []
        for _ in range(51):
            queues.append(manager.create_connection())
        assert manager.connection_count == 51


class TestEmitStateChangeBroadcastsToSSE:
    """Test emit_state_change SSE broadcast."""

    @pytest.mark.asyncio
    async def test_broadcasts_event_to_connections(self):
        """emit_state_change should broadcast event data to SSE connections."""
        # Use a fresh EventManager to avoid affecting the singleton
        manager = EventManager()
        queue = manager.create_connection()

        with patch("app.core.events.event_manager", manager):
            await emit_state_change(
                review_id=1,
                old_state="PENDING",
                new_state="POLICY_EVAL",
                source_system="test-system",
            )

        data = queue.get_nowait()
        assert data["review_id"] == 1
        assert data["old_state"] == "PENDING"
        assert data["new_state"] == "POLICY_EVAL"
        assert data["source_system"] == "test-system"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_handles_no_arq_pool_gracefully(self):
        """emit_state_change should not raise when arq_pool is None."""
        manager = EventManager()

        mock_app = MagicMock()
        mock_app.state.arq_pool = None

        with patch("app.core.events.event_manager", manager):
            with patch("app.main.app", mock_app):
                # Should not raise
                await emit_state_change(
                    review_id=1,
                    old_state="PENDING",
                    new_state="COMPLETE",
                    source_system="test",
                )

    @pytest.mark.asyncio
    async def test_handles_webhook_enqueue_exception(self):
        """emit_state_change should catch and log exceptions from webhook enqueue."""
        manager = EventManager()
        queue = manager.create_connection()

        with patch("app.core.events.event_manager", manager):
            # The inner import block will fail because there's no real DB,
            # but emit_state_change should catch and log the error
            await emit_state_change(
                review_id=1,
                old_state="PENDING",
                new_state="POLICY_EVAL",
                source_system="test",
            )

        # SSE broadcast should still have succeeded
        data = queue.get_nowait()
        assert data["review_id"] == 1
