"""Tests for batch approve/reject endpoints.

Verifies batch approval and rejection with partial success,
validation, and audit trail creation.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.state_machine import transition_state
from app.models.schema import AuditEntry, Review
from app.models.schemas import ReviewState


class TestBatchApprove:
    """Test batch approve endpoint logic at the core module level."""

    async def _create_approving_review(self, session, **overrides) -> Review:
        """Create a review and advance it to APPROVING state."""
        defaults = {
            "type": "video_review",
            "content_ref": f"s3://bucket/video-{id(overrides)}.mp4",
            "source_system": "kais-movie-agent",
            "priority": "normal",
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
    async def test_batch_approve_multiple_reviews(self, db_session):
        """Multiple reviews can be approved in a single batch."""
        r1 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/batch-1.mp4"
        )
        r2 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/batch-2.mp4"
        )
        r3 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/batch-3.mp4"
        )

        # Simulate batch approve: approve each independently
        actor = "client:test-client"
        success_ids = []
        for review_id in [r1.id, r2.id, r3.id]:
            review = await db_session.get(Review, review_id)
            result = await transition_state(
                db_session,
                review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                review.version,
                actor,
                action="batch_approve",
                payload={"comment": "batch test", "batch": True},
            )
            success_ids.append(result.id)

        assert len(success_ids) == 3
        for rid in success_ids:
            review = await db_session.get(Review, rid)
            assert review.state == ReviewState.COMPLETE.value

    @pytest.mark.asyncio
    async def test_batch_reject_multiple_reviews(self, db_session):
        """Multiple reviews can be rejected in a single batch."""
        r1 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/reject-1.mp4"
        )
        r2 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/reject-2.mp4"
        )

        actor = "client:test-client"
        for review_id in [r1.id, r2.id]:
            review = await db_session.get(Review, review_id)
            await transition_state(
                db_session,
                review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                review.version,
                actor,
                action="batch_reject",
                payload={"reason": "batch reject test", "batch": True},
            )

        for rid in [r1.id, r2.id]:
            review = await db_session.get(Review, rid)
            assert review.state == ReviewState.COMPLETE.value

    @pytest.mark.asyncio
    async def test_partial_success_wrong_state(self, db_session):
        """Batch with some reviews in wrong state: partial success."""
        # One review in APPROVING
        r1 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/partial-1.mp4"
        )
        # One review stays in PENDING
        r2 = Review(
            type="video_review",
            content_ref="s3://bucket/partial-2.mp4",
            source_system="kais-movie-agent",
            priority="normal",
            risk_score=0.5,
            state=ReviewState.PENDING.value,
            version=1,
        )
        db_session.add(r2)
        await db_session.commit()
        await db_session.refresh(r2)

        actor = "client:test-client"
        results = []
        for review_id in [r1.id, r2.id]:
            review = await db_session.get(Review, review_id)
            if review.state != ReviewState.APPROVING.value:
                results.append({"review_id": review_id, "status": "failed"})
                continue
            await transition_state(
                db_session,
                review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                review.version,
                actor,
                action="batch_approve",
                payload={"comment": "partial test", "batch": True},
            )
            results.append({"review_id": review_id, "status": "success"})

        assert results[0]["status"] == "success"  # r1 was APPROVING
        assert results[1]["status"] == "failed"   # r2 was PENDING

    @pytest.mark.asyncio
    async def test_batch_creates_audit_trail(self, db_session):
        """Each batch item creates its own audit trail entry."""
        r1 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/audit-1.mp4"
        )
        r2 = await self._create_approving_review(
            db_session, content_ref="s3://bucket/audit-2.mp4"
        )

        actor = "client:test-client"
        for review_id in [r1.id, r2.id]:
            review = await db_session.get(Review, review_id)
            await transition_state(
                db_session,
                review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                review.version,
                actor,
                action="batch_approve",
                payload={"comment": "audit test", "batch": True},
            )

        # Verify audit entries
        for review_id in [r1.id, r2.id]:
            stmt = (
                select(AuditEntry)
                .where(
                    AuditEntry.review_id == review_id,
                    AuditEntry.action == "batch_approve",
                )
            )
            result = await db_session.execute(stmt)
            entries = result.scalars().all()
            assert len(entries) >= 1, f"No batch_approve audit for review {review_id}"
            entry = entries[-1]
            assert entry.payload.get("batch") is True
            assert entry.payload.get("comment") == "audit test"


class TestBatchSchemas:
    """Test batch request/response Pydantic schemas."""

    def test_batch_approve_request_valid(self):
        from app.models.schemas import BatchApproveRequest
        req = BatchApproveRequest(review_ids=[1, 2, 3], comment="test")
        assert len(req.review_ids) == 3
        assert req.comment == "test"

    def test_batch_approve_request_no_comment(self):
        from app.models.schemas import BatchApproveRequest
        req = BatchApproveRequest(review_ids=[1])
        assert req.comment is None

    def test_batch_approve_request_empty_ids_fails(self):
        from app.models.schemas import BatchApproveRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BatchApproveRequest(review_ids=[])

    def test_batch_approve_request_too_many_ids_fails(self):
        from app.models.schemas import BatchApproveRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BatchApproveRequest(review_ids=list(range(1, 102)))

    def test_batch_reject_request_valid(self):
        from app.models.schemas import BatchRejectRequest
        req = BatchRejectRequest(review_ids=[1, 2], reason="bad content")
        assert len(req.review_ids) == 2
        assert req.reason == "bad content"

    def test_batch_reject_request_empty_reason_fails(self):
        from app.models.schemas import BatchRejectRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BatchRejectRequest(review_ids=[1], reason="")

    def test_batch_response_serialization(self):
        from app.models.schemas import BatchResponse, BatchItemResult
        resp = BatchResponse(
            total=3,
            success_count=2,
            failure_count=1,
            items=[
                BatchItemResult(review_id=1, status="success"),
                BatchItemResult(review_id=2, status="success"),
                BatchItemResult(review_id=3, status="failed", error="wrong state"),
            ],
        )
        data = resp.model_dump()
        assert data["total"] == 3
        assert data["success_count"] == 2
        assert data["failure_count"] == 1
        assert len(data["items"]) == 3

    def test_batch_item_result_defaults(self):
        from app.models.schemas import BatchItemResult
        item = BatchItemResult(review_id=1, status="success")
        assert item.error is None

    def test_max_batch_size_100(self):
        from app.models.schemas import BatchApproveRequest
        from pydantic import ValidationError
        # Exactly 100 should pass
        req = BatchApproveRequest(review_ids=list(range(1, 101)))
        assert len(req.review_ids) == 100
        # 101 should fail
        with pytest.raises(ValidationError):
            BatchApproveRequest(review_ids=list(range(1, 102)))
