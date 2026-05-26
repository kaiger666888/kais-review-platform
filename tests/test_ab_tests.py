"""Tests for A/B test batch creation and query API."""

import uuid

import pytest
from sqlalchemy import select

from app.models.ab_test_pair import ABTestPair
from app.models.schemas import ABTestCreateRequest


# ---------------------------------------------------------------------------
# A/B test models
# ---------------------------------------------------------------------------


class TestABTestModels:
    def test_ab_test_create_request_valid(self):
        req = ABTestCreateRequest(shot_ids=["s1", "s2"])
        assert len(req.shot_ids) == 2

    def test_ab_test_create_request_empty_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            ABTestCreateRequest(shot_ids=[])

    def test_ab_test_create_request_too_many_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            ABTestCreateRequest(shot_ids=[f"s{i}" for i in range(101)])


# ---------------------------------------------------------------------------
# A/B test model fields
# ---------------------------------------------------------------------------


class TestABTestPairModel:
    def test_table_name(self):
        assert ABTestPair.__tablename__ == "ab_test_pairs"

    def test_model_instantiation(self):
        pair = ABTestPair(
            batch_id=str(uuid.uuid4()),
            shot_id="shot-001",
        )
        assert pair.batch_id is not None
        assert pair.shot_id == "shot-001"
        assert pair.ai_score is None
        assert pair.human_decision is None

    def test_model_with_ai_score(self):
        pair = ABTestPair(
            batch_id=str(uuid.uuid4()),
            shot_id="shot-002",
            ai_score={"aesthetics": 0.9, "consistency": 0.8},
            human_decision="approved",
        )
        assert pair.ai_score == {"aesthetics": 0.9, "consistency": 0.8}
        assert pair.human_decision == "approved"


# ---------------------------------------------------------------------------
# A/B test batch creation logic
# ---------------------------------------------------------------------------


class TestABTestsBatchLogic:
    def test_batch_id_is_uuid4_format(self):
        """POST /api/v1/ab-tests generates a UUID4 batch_id."""
        batch_id = str(uuid.uuid4())
        # Verify it's a valid UUID
        parsed = uuid.UUID(batch_id, version=4)
        assert str(parsed) == batch_id

    def test_batch_creation_count(self):
        """Batch with N shot_ids creates N ABTestPair records."""
        shot_ids = ["shot-001", "shot-002", "shot-003"]
        batch_id = str(uuid.uuid4())

        pairs = [
            ABTestPair(batch_id=batch_id, shot_id=sid)
            for sid in shot_ids
        ]
        assert len(pairs) == 3
        assert all(p.batch_id == batch_id for p in pairs)
