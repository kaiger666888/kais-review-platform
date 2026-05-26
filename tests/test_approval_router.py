"""Tests for the ApprovalRouter service: priority queue ordering.

Verifies that the approval queue returns reviews sorted by priority weight
(critical > high > normal > low), then by created_at ascending within the
same priority tier.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from app.core.state_machine import transition_state
from app.models.schema import Review
from app.models.schemas import ReviewState
from app.services.approval_router import (
    PRIORITY_WEIGHT,
    build_approval_queue_query,
    get_priority_sorted_reviews,
)


class TestPriorityWeight:
    """Test priority weight mapping."""

    def test_critical_is_highest(self):
        assert PRIORITY_WEIGHT["critical"] > PRIORITY_WEIGHT["high"]

    def test_high_above_normal(self):
        assert PRIORITY_WEIGHT["high"] > PRIORITY_WEIGHT["normal"]

    def test_normal_above_low(self):
        assert PRIORITY_WEIGHT["normal"] > PRIORITY_WEIGHT["low"]

    def test_all_priorities_mapped(self):
        assert set(PRIORITY_WEIGHT.keys()) == {"critical", "high", "normal", "low"}

    def test_weights_are_positive(self):
        for priority, weight in PRIORITY_WEIGHT.items():
            assert weight > 0, f"{priority} has non-positive weight {weight}"


class TestApprovalQueueOrdering:
    """Test that the approval queue returns reviews in correct priority order."""

    async def _create_approving_review(
        self, session, priority: str, created_minutes_ago: int = 0, **overrides
    ) -> Review:
        """Create a review and advance it to APPROVING state."""
        defaults = {
            "type": "video_review",
            "content_ref": f"s3://bucket/video-{priority}-{id(overrides)}.mp4",
            "source_system": "kais-movie-agent",
            "priority": priority,
            "risk_score": 0.8,
            "state": ReviewState.PENDING.value,
            "version": 1,
            "metadata_json": None,
        }
        defaults.update(overrides)
        r = Review(**defaults)
        session.add(r)
        await session.commit()
        await session.refresh(r)

        # Advance to APPROVING
        r = await transition_state(
            session, r.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
            r.version, actor="system", action="policy_eval_start",
        )
        r = await transition_state(
            session, r.id, ReviewState.POLICY_EVAL, ReviewState.APPROVING,
            r.version, actor="system", action="route_human",
            payload={"disposition": "HUMAN"},
        )
        return r

    @pytest.mark.asyncio
    async def test_critical_before_normal(self, db_session):
        """Critical reviews appear before normal reviews in the queue."""
        normal = await self._create_approving_review(db_session, "normal")
        critical = await self._create_approving_review(db_session, "critical")

        result = await get_priority_sorted_reviews(db_session)
        assert len(result) == 2
        assert result[0].priority == "critical"
        assert result[1].priority == "normal"

    @pytest.mark.asyncio
    async def test_priority_ordering_full(self, db_session):
        """All four priority levels are correctly ordered."""
        low = await self._create_approving_review(db_session, "low")
        normal = await self._create_approving_review(db_session, "normal")
        high = await self._create_approving_review(db_session, "high")
        critical = await self._create_approving_review(db_session, "critical")

        result = await get_priority_sorted_reviews(db_session)
        assert len(result) == 4
        assert result[0].priority == "critical"
        assert result[1].priority == "high"
        assert result[2].priority == "normal"
        assert result[3].priority == "low"

    @pytest.mark.asyncio
    async def test_same_priority_oldest_first(self, db_session):
        """Within same priority, older reviews (lower created_at) appear first."""
        r1 = await self._create_approving_review(db_session, "normal", content_ref="s3://bucket/first.mp4")
        r2 = await self._create_approving_review(db_session, "normal", content_ref="s3://bucket/second.mp4")

        result = await get_priority_sorted_reviews(db_session)
        assert len(result) == 2
        # Both are normal priority, so order is by created_at ascending
        assert result[0].id == r1.id  # r1 created first
        assert result[1].id == r2.id  # r2 created second

    @pytest.mark.asyncio
    async def test_empty_queue(self, db_session):
        """Empty queue returns empty list."""
        result = await get_priority_sorted_reviews(db_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_only_approving_state_included(self, db_session):
        """Reviews not in APPROVING state are excluded from the queue."""
        # Create a PENDING review (not advanced)
        r = Review(
            type="video_review",
            content_ref="s3://bucket/pending.mp4",
            source_system="kais-movie-agent",
            priority="critical",
            risk_score=0.9,
            state=ReviewState.PENDING.value,
            version=1,
        )
        db_session.add(r)
        await db_session.commit()

        result = await get_priority_sorted_reviews(db_session)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_limit_parameter(self, db_session):
        """Limit parameter restricts the number of results."""
        for i in range(5):
            await self._create_approving_review(
                db_session, "normal",
                content_ref=f"s3://bucket/limit-{i}.mp4",
            )

        result = await get_priority_sorted_reviews(db_session, limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_build_approval_queue_query_returns_select(self):
        """build_approval_queue_query returns a SQLAlchemy Select object."""
        from sqlalchemy import Select
        query = build_approval_queue_query(limit=10, offset=0)
        assert isinstance(query, Select)
