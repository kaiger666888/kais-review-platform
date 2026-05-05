"""Integration tests for the full review submission flow.

Tests the critical path: submit -> policy eval -> route -> state transitions.
These tests work at the core module level since the HTTP endpoints (Plan 04)
may not yet be available. The tests validate the same business logic the
endpoints would exercise.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.policy import PolicyEngine
from app.core.state_machine import transition_state
from app.models.schema import AuditEntry, Review
from app.models.schemas import Disposition, ReviewState


class TestSubmitFlow:
    """Test review submission through the core modules."""

    @pytest.fixture
    def engine(self):
        """Provide a PolicyEngine loaded with the default routing policy."""
        import os
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app",
            "policies",
            "default.yaml",
        )
        engine = PolicyEngine()
        engine.load_from_file(default_path)
        return engine

    async def _create_review(self, session, **overrides):
        """Create a review in PENDING state with the given attributes."""
        defaults = {
            "type": "video_review",
            "content_ref": "s3://bucket/video-001.mp4",
            "source_system": "kais-movie-agent",
            "priority": "normal",
            "risk_score": 0.5,
            "state": ReviewState.PENDING.value,
            "version": 1,
            "metadata_json": None,
        }
        defaults.update(overrides)
        r = Review(**defaults)
        session.add(r)
        await session.commit()
        await session.refresh(r)
        return r

    async def _run_policy_eval(self, engine, review, session):
        """Simulate the policy evaluation step.

        Transitions PENDING -> POLICY_EVAL, then evaluates the policy
        to determine the disposition and next state.
        """
        # Transition to POLICY_EVAL
        review = await transition_state(
            session, review.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
            review.version, actor="system", action="policy_eval_start",
        )

        # Evaluate policy
        review_data = {
            "risk_score": review.risk_score,
            "source_system": review.source_system,
            "priority": review.priority,
        }
        if review.metadata_json:
            review_data["metadata"] = review.metadata_json

        disposition = engine.evaluate(review_data)

        # Route based on disposition
        if disposition == Disposition.AUTO:
            # Auto-approved -> COMPLETE
            review = await transition_state(
                session, review.id, ReviewState.POLICY_EVAL, ReviewState.COMPLETE,
                review.version, actor="system", action="auto_approve",
                payload={"disposition": disposition.value},
            )
        elif disposition == Disposition.BLOCK:
            # Blocked -> COMPLETE
            review = await transition_state(
                session, review.id, ReviewState.POLICY_EVAL, ReviewState.COMPLETE,
                review.version, actor="system", action="blocked",
                payload={"disposition": disposition.value},
            )
        else:
            # HUMAN or AI_AUDIT -> APPROVING
            review = await transition_state(
                session, review.id, ReviewState.POLICY_EVAL, ReviewState.APPROVING,
                review.version, actor="system", action="route_" + disposition.value.lower(),
                payload={"disposition": disposition.value},
            )

        return review, disposition

    @pytest.mark.asyncio
    async def test_low_risk_auto_approved(self, db_session, engine):
        """Low-risk review from movie-agent is auto-approved (COMPLETE)."""
        review = await self._create_review(
            db_session, risk_score=0.1, source_system="kais-movie-agent"
        )
        result, disposition = await self._run_policy_eval(engine, review, db_session)

        assert disposition == Disposition.AUTO
        assert result.state == ReviewState.COMPLETE.value
        assert result.version == 3  # PENDING(1) -> POLICY_EVAL(2) -> COMPLETE(3)

    @pytest.mark.asyncio
    async def test_high_risk_routed_to_human(self, db_session, engine):
        """High-risk review routes to HUMAN (APPROVING state)."""
        review = await self._create_review(
            db_session, risk_score=0.8, source_system="kais-movie-agent"
        )
        result, disposition = await self._run_policy_eval(engine, review, db_session)

        assert disposition == Disposition.HUMAN
        assert result.state == ReviewState.APPROVING.value
        assert result.version == 3  # PENDING(1) -> POLICY_EVAL(2) -> APPROVING(3)

    @pytest.mark.asyncio
    async def test_flagged_content_blocked(self, db_session, engine):
        """Flagged content is blocked and moved to COMPLETE."""
        review = await self._create_review(
            db_session,
            risk_score=0.5,
            source_system="kais-gold-team",
            metadata_json={"flagged": True},
        )
        result, disposition = await self._run_policy_eval(engine, review, db_session)

        assert disposition == Disposition.BLOCK
        assert result.state == ReviewState.COMPLETE.value

    @pytest.mark.asyncio
    async def test_critical_priority_routed_to_human(self, db_session, engine):
        """Critical priority triggers HUMAN review regardless of risk."""
        review = await self._create_review(
            db_session, risk_score=0.5, priority="critical",
            source_system="kais-gold-team",
        )
        result, disposition = await self._run_policy_eval(engine, review, db_session)

        assert disposition == Disposition.HUMAN
        assert result.state == ReviewState.APPROVING.value

    @pytest.mark.asyncio
    async def test_full_approve_flow(self, db_session, engine):
        """Full lifecycle: submit -> policy eval -> human route -> approve."""
        review = await self._create_review(
            db_session, risk_score=0.8, source_system="kais-movie-agent"
        )
        result, disposition = await self._run_policy_eval(engine, review, db_session)
        assert result.state == ReviewState.APPROVING.value

        # Approve the review
        result = await transition_state(
            db_session, result.id, ReviewState.APPROVING, ReviewState.COMPLETE,
            result.version, actor="reviewer-1", action="approve",
            payload={"comment": "Looks good"},
        )
        assert result.state == ReviewState.COMPLETE.value
        assert result.version == 4

    @pytest.mark.asyncio
    async def test_full_reject_flow(self, db_session, engine):
        """Full lifecycle: submit -> policy eval -> human route -> reject."""
        review = await self._create_review(
            db_session, risk_score=0.8, source_system="kais-movie-agent"
        )
        result, disposition = await self._run_policy_eval(engine, review, db_session)
        assert result.state == ReviewState.APPROVING.value

        # Reject the review
        result = await transition_state(
            db_session, result.id, ReviewState.APPROVING, ReviewState.COMPLETE,
            result.version, actor="reviewer-1", action="reject",
            payload={"reason": "Content violates safety guidelines"},
        )
        assert result.state == ReviewState.COMPLETE.value

    @pytest.mark.asyncio
    async def test_submit_creates_audit_trail(self, db_session, engine):
        """Full submission flow creates proper audit trail entries."""
        review = await self._create_review(
            db_session, risk_score=0.1, source_system="kais-movie-agent"
        )
        await self._run_policy_eval(engine, review, db_session)

        stmt = (
            select(AuditEntry)
            .where(AuditEntry.review_id == review.id)
            .order_by(AuditEntry.id)
        )
        result = await db_session.execute(stmt)
        entries = result.scalars().all()

        # Should have at least 2 entries: policy_eval_start + auto_approve
        assert len(entries) >= 2
        assert entries[0].action == "policy_eval_start"
        assert entries[-1].action == "auto_approve"

        # Verify hash chain integrity
        for i in range(1, len(entries)):
            assert entries[i].prev_hash == entries[i - 1].own_hash

    @pytest.mark.asyncio
    async def test_cannot_approve_auto_review(self, db_session, engine):
        """Auto-approved review (COMPLETE) cannot be transitioned again."""
        review = await self._create_review(
            db_session, risk_score=0.1, source_system="kais-movie-agent"
        )
        result, _ = await self._run_policy_eval(engine, review, db_session)
        assert result.state == ReviewState.COMPLETE.value

        from app.core.state_machine import InvalidTransitionError
        with pytest.raises(InvalidTransitionError):
            await transition_state(
                db_session, result.id, ReviewState.COMPLETE, ReviewState.APPROVING,
                result.version, actor="reviewer-1",
            )

    @pytest.mark.asyncio
    async def test_multiple_reviews_independent(self, db_session, engine):
        """Multiple reviews progress independently through the state machine."""
        r1 = await self._create_review(
            db_session, risk_score=0.1, source_system="kais-movie-agent"
        )
        r2 = await self._create_review(
            db_session, risk_score=0.8, source_system="kais-movie-agent",
            content_ref="s3://bucket/video-002.mp4",
        )

        r1_result, d1 = await self._run_policy_eval(engine, r1, db_session)
        r2_result, d2 = await self._run_policy_eval(engine, r2, db_session)

        assert d1 == Disposition.AUTO
        assert r1_result.state == ReviewState.COMPLETE.value

        assert d2 == Disposition.HUMAN
        assert r2_result.state == ReviewState.APPROVING.value

        assert r1_result.id != r2_result.id
