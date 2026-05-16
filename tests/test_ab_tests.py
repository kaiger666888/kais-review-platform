"""Tests for A/B test batch creation and query API."""

import pytest
from httpx import ASGITransport, AsyncClient

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
# A/B test API endpoints (integration-style via TestClient)
# ---------------------------------------------------------------------------


class TestABTestsAPI:
    @pytest.mark.asyncio
    async def test_create_batch(self, db_engine):
        from app.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/ab-tests/",
                json={"shot_ids": ["shot-001", "shot-002"]},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert "data" in data
            batch_data = data["data"]
            assert "batch_id" in batch_data
            assert batch_data["total"] == 2

    @pytest.mark.asyncio
    async def test_get_batch_by_id(self, db_engine):
        from app.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create a batch first
            create_resp = await client.post(
                "/api/v1/ab-tests/",
                json={"shot_ids": ["shot-101", "shot-102"]},
            )
            assert create_resp.status_code == 201
            batch_id = create_resp.json()["data"]["batch_id"]

            # Query the batch
            get_resp = await client.get(f"/api/v1/ab-tests/{batch_id}")
            assert get_resp.status_code == 200
            pairs = get_resp.json()["data"]
            assert len(pairs) == 2
            shot_ids = {p["shot_id"] for p in pairs}
            assert shot_ids == {"shot-101", "shot-102"}
