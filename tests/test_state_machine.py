"""Unit tests for the 4-state checkpoint state machine.

Tests all valid transitions, invalid transitions, terminal state protection,
optimistic locking conflicts, and escalation paths.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine import (
    InvalidTransitionError,
    StateConflictError,
    TerminalStateError,
    get_allowed_transitions,
    is_terminal,
    transition_state,
    validate_transition,
)
from app.models.schema import AuditEntry, Review
from app.models.schemas import ReviewState


class TestTransitionValidation:
    """Test the validate_transition helper and transition map."""

    def test_pending_to_policy_eval_is_valid(self):
        assert validate_transition(ReviewState.PENDING, ReviewState.POLICY_EVAL) is True

    def test_policy_eval_to_approving_is_valid(self):
        assert validate_transition(ReviewState.POLICY_EVAL, ReviewState.APPROVING) is True

    def test_policy_eval_to_complete_is_valid(self):
        assert validate_transition(ReviewState.POLICY_EVAL, ReviewState.COMPLETE) is True

    def test_approving_to_complete_is_valid(self):
        assert validate_transition(ReviewState.APPROVING, ReviewState.COMPLETE) is True

    def test_approving_to_pending_is_valid(self):
        assert validate_transition(ReviewState.APPROVING, ReviewState.PENDING) is True

    def test_approving_to_policy_eval_is_valid(self):
        assert validate_transition(ReviewState.APPROVING, ReviewState.POLICY_EVAL) is True

    def test_pending_to_complete_is_invalid(self):
        assert validate_transition(ReviewState.PENDING, ReviewState.COMPLETE) is False

    def test_complete_to_pending_is_invalid(self):
        assert validate_transition(ReviewState.COMPLETE, ReviewState.PENDING) is False

    def test_complete_to_approving_is_invalid(self):
        assert validate_transition(ReviewState.COMPLETE, ReviewState.APPROVING) is False

    def test_complete_is_terminal(self):
        assert is_terminal(ReviewState.COMPLETE) is True

    def test_pending_is_not_terminal(self):
        assert is_terminal(ReviewState.PENDING) is False

    def test_get_allowed_transitions_from_pending(self):
        allowed = get_allowed_transitions(ReviewState.PENDING)
        assert ReviewState.POLICY_EVAL in allowed
        assert len(allowed) == 1

    def test_get_allowed_transitions_from_complete_is_empty(self):
        allowed = get_allowed_transitions(ReviewState.COMPLETE)
        assert len(allowed) == 0

    def test_get_allowed_transitions_returns_copy(self):
        """Verify returned set is a copy, not the internal set."""
        allowed = get_allowed_transitions(ReviewState.PENDING)
        allowed.add(ReviewState.COMPLETE)  # Modify the copy
        # Original should be unchanged
        assert ReviewState.COMPLETE not in get_allowed_transitions(ReviewState.PENDING)


class TestTransitionState:
    """Test the transition_state function with database operations."""

    @pytest_asyncio.fixture
    async def review(self, db_session):
        """Create a test review in PENDING state."""
        r = Review(
            type="video_review",
            content_ref="s3://bucket/video-001.mp4",
            source_system="kais-movie-agent",
            priority="normal",
            risk_score=0.5,
            state=ReviewState.PENDING.value,
            version=1,
        )
        db_session.add(r)
        await db_session.commit()
        await db_session.refresh(r)
        return r

    async def _transition(self, session, review, from_state, to_state, **kwargs):
        """Helper to transition a review."""
        return await transition_state(
            session,
            review.id,
            from_state,
            to_state,
            review.version,
            actor=kwargs.get("actor", "test"),
            action=kwargs.get("action"),
            payload=kwargs.get("payload"),
        )

    @pytest.mark.asyncio
    async def test_pending_to_policy_eval(self, db_session, review):
        result = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        assert result.state == ReviewState.POLICY_EVAL.value
        assert result.version == 2

    @pytest.mark.asyncio
    async def test_full_lifecycle_to_complete(self, db_session, review):
        """PENDING -> POLICY_EVAL -> APPROVING -> COMPLETE"""
        r = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        assert r.state == ReviewState.POLICY_EVAL.value
        assert r.version == 2

        r = await self._transition(
            db_session, r, ReviewState.POLICY_EVAL, ReviewState.APPROVING
        )
        assert r.state == ReviewState.APPROVING.value
        assert r.version == 3

        r = await self._transition(
            db_session, r, ReviewState.APPROVING, ReviewState.COMPLETE
        )
        assert r.state == ReviewState.COMPLETE.value
        assert r.version == 4

    @pytest.mark.asyncio
    async def test_auto_approve_lifecycle(self, db_session, review):
        """PENDING -> POLICY_EVAL -> COMPLETE (auto-approved)"""
        r = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        r = await self._transition(
            db_session, r, ReviewState.POLICY_EVAL, ReviewState.COMPLETE
        )
        assert r.state == ReviewState.COMPLETE.value
        assert r.version == 3

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, db_session, review):
        """PENDING -> COMPLETE is invalid."""
        with pytest.raises(InvalidTransitionError, match="Invalid transition"):
            await self._transition(
                db_session, review, ReviewState.PENDING, ReviewState.COMPLETE
            )

    @pytest.mark.asyncio
    async def test_terminal_state_raises(self, db_session, review):
        """Cannot transition from COMPLETE -- raises InvalidTransitionError
        since COMPLETE has no valid outgoing transitions."""
        r = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        r = await self._transition(
            db_session, r, ReviewState.POLICY_EVAL, ReviewState.COMPLETE
        )
        # COMPLETE -> PENDING is invalid (no valid transitions from COMPLETE)
        with pytest.raises(InvalidTransitionError, match="Invalid transition"):
            await self._transition(
                db_session, r, ReviewState.COMPLETE, ReviewState.PENDING
            )

    @pytest.mark.asyncio
    async def test_optimistic_locking_conflict(self, db_session, review):
        """Second transition with stale version raises StateConflictError."""
        # First transition succeeds (version 1 -> 2)
        await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )

        # Second transition with stale version 1 fails
        with pytest.raises(StateConflictError, match="State conflict"):
            await transition_state(
                db_session,
                review.id,
                ReviewState.PENDING,
                ReviewState.POLICY_EVAL,
                expected_version=1,  # Stale version
                actor="test",
            )

    @pytest.mark.asyncio
    async def test_wrong_from_state_raises_conflict(self, db_session, review):
        """Transition with wrong from_state raises StateConflictError."""
        with pytest.raises(StateConflictError):
            await transition_state(
                db_session,
                review.id,
                ReviewState.APPROVING,  # Wrong - review is actually PENDING
                ReviewState.COMPLETE,
                expected_version=1,
                actor="test",
            )

    @pytest.mark.asyncio
    async def test_escalate_from_approving_to_pending(self, db_session, review):
        """APPROVING -> PENDING escalation (e.g., reviewer unavailable)."""
        r = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        r = await self._transition(
            db_session, r, ReviewState.POLICY_EVAL, ReviewState.APPROVING
        )
        r = await self._transition(
            db_session, r, ReviewState.APPROVING, ReviewState.PENDING
        )
        assert r.state == ReviewState.PENDING.value
        assert r.version == 4

    @pytest.mark.asyncio
    async def test_escalate_from_approving_to_policy_eval(self, db_session, review):
        """APPROVING -> POLICY_EVAL (timeout re-evaluation)."""
        r = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        r = await self._transition(
            db_session, r, ReviewState.POLICY_EVAL, ReviewState.APPROVING
        )
        r = await self._transition(
            db_session, r, ReviewState.APPROVING, ReviewState.POLICY_EVAL,
            actor="timeout",
            action="auto_escalate",
        )
        assert r.state == ReviewState.POLICY_EVAL.value
        assert r.version == 4

    @pytest.mark.asyncio
    async def test_transition_creates_audit_entry(self, db_session, review):
        """Each transition creates an audit trail entry."""
        await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL,
            action="evaluate_policy",
        )

        stmt = select(AuditEntry).where(AuditEntry.review_id == review.id)
        result = await db_session.execute(stmt)
        entries = result.scalars().all()

        assert len(entries) >= 1
        entry = entries[-1]
        assert entry.action == "evaluate_policy"
        assert entry.from_state == ReviewState.PENDING.value
        assert entry.to_state == ReviewState.POLICY_EVAL.value
        assert entry.actor == "test"
        assert entry.prev_hash is not None
        assert entry.own_hash is not None

    @pytest.mark.asyncio
    async def test_multiple_transitions_create_hash_chain(self, db_session, review):
        """Multiple transitions create a linked hash chain in audit entries."""
        r = await self._transition(
            db_session, review, ReviewState.PENDING, ReviewState.POLICY_EVAL
        )
        r = await self._transition(
            db_session, r, ReviewState.POLICY_EVAL, ReviewState.APPROVING
        )
        r = await self._transition(
            db_session, r, ReviewState.APPROVING, ReviewState.COMPLETE
        )

        stmt = (
            select(AuditEntry)
            .where(AuditEntry.review_id == review.id)
            .order_by(AuditEntry.id)
        )
        result = await db_session.execute(stmt)
        entries = result.scalars().all()

        assert len(entries) == 3
        # Each entry's prev_hash must match the previous entry's own_hash
        for i in range(1, len(entries)):
            assert entries[i].prev_hash == entries[i - 1].own_hash
