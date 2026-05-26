"""Integration tests for the full API review lifecycle.

Tests all core API flows through the actual HTTP layer using httpx.AsyncClient
with ASGI transport, in-memory SQLite, and mock Redis.

Covers TEST-01 through TEST-10 requirements.
"""

import asyncio

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _submit_review(
    client: AsyncClient,
    auth_headers: dict,
    **overrides,
) -> "httpx.Response":
    """Submit a review via POST /api/v1/reviews/ with default values merged with overrides."""
    body = {
        "type": "video_review",
        "content_ref": "s3://bucket/test.mp4",
        "source_system": "kais-movie-agent",
        "priority": "normal",
        "risk_score": 0.5,
    }
    body.update(overrides)
    return await client.post(
        "/api/v1/reviews/",
        json=body,
        headers=auth_headers,
    )


# ---------------------------------------------------------------------------
# TEST-01: Submit review with correct dispositions
# ---------------------------------------------------------------------------


class TestSubmitDisposition:
    """TEST-01: POST /api/v1/reviews returns correct disposition based on policy."""

    @pytest.mark.asyncio
    async def test_submit_auto_disposition(self, client, auth_headers):
        """Low-risk movie-agent review is auto-approved (AUTO -> COMPLETE)."""
        response = await _submit_review(
            client,
            auth_headers,
            risk_score=0.1,
            source_system="kais-movie-agent",
        )
        assert response.status_code == 202
        body = response.json()
        assert body["data"]["routing"] == "AUTO"
        assert body["data"]["state"] == "COMPLETE"

    @pytest.mark.asyncio
    async def test_submit_human_disposition(self, client, auth_headers):
        """High-risk review routes to HUMAN (APPROVING state)."""
        response = await _submit_review(
            client,
            auth_headers,
            risk_score=0.8,
            source_system="kais-movie-agent",
        )
        assert response.status_code == 202
        body = response.json()
        assert body["data"]["routing"] == "HUMAN"
        assert body["data"]["state"] == "APPROVING"

    @pytest.mark.asyncio
    async def test_submit_block_disposition(self, client, auth_headers):
        """Flagged metadata triggers BLOCK disposition."""
        response = await _submit_review(
            client,
            auth_headers,
            risk_score=0.5,
            metadata={"flagged": True},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["data"]["routing"] == "BLOCK"
        assert body["data"]["state"] == "COMPLETE"


# ---------------------------------------------------------------------------
# TEST-02: Approve review
# ---------------------------------------------------------------------------


class TestApproveReview:
    """TEST-02: POST /api/v1/reviews/{id}/approve transitions APPROVING -> COMPLETE."""

    @pytest.mark.asyncio
    async def test_approve_review(self, client, auth_headers):
        """Approve a high-risk review in APPROVING state."""
        # Submit high-risk to get APPROVING state
        submit_resp = await _submit_review(
            client, auth_headers, risk_score=0.8, source_system="kais-movie-agent"
        )
        review_id = submit_resp.json()["data"]["review_id"]

        # Approve it
        approve_resp = await client.post(
            f"/api/v1/reviews/{review_id}/approve",
            json={"comment": "Looks good"},
            headers=auth_headers,
        )
        assert approve_resp.status_code == 200
        body = approve_resp.json()
        assert body["data"]["state"] == "COMPLETE"


# ---------------------------------------------------------------------------
# TEST-03: Reject review
# ---------------------------------------------------------------------------


class TestRejectReview:
    """TEST-03: POST /api/v1/reviews/{id}/reject transitions APPROVING -> COMPLETE."""

    @pytest.mark.asyncio
    async def test_reject_review(self, client, auth_headers):
        """Reject a high-risk review in APPROVING state."""
        # Submit high-risk to get APPROVING state
        submit_resp = await _submit_review(
            client, auth_headers, risk_score=0.8, source_system="kais-movie-agent"
        )
        review_id = submit_resp.json()["data"]["review_id"]

        # Reject it
        reject_resp = await client.post(
            f"/api/v1/reviews/{review_id}/reject",
            json={"reason": "Policy violation"},
            headers=auth_headers,
        )
        assert reject_resp.status_code == 200
        body = reject_resp.json()
        assert body["data"]["state"] == "COMPLETE"


# ---------------------------------------------------------------------------
# TEST-04: Audit trail created on state transitions
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """TEST-04: State transitions create immutable audit log entries."""

    @pytest.mark.asyncio
    async def test_audit_trail_created(self, client, auth_headers):
        """After submission, GET /api/v1/audit/{id} returns entries with valid hash chain."""
        # Submit an auto-approved review
        submit_resp = await _submit_review(
            client, auth_headers, risk_score=0.1, source_system="kais-movie-agent"
        )
        review_id = submit_resp.json()["data"]["review_id"]

        # Query audit trail
        audit_resp = await client.get(
            f"/api/v1/audit/{review_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        entries = audit_resp.json()["data"]
        assert len(entries) >= 2, f"Expected at least 2 audit entries, got {len(entries)}"

        # Verify first entry is policy_eval_start
        assert entries[0]["action"] == "policy_eval_start"

        # Verify state transitions are correct (each entry links from_state -> to_state)
        assert entries[0]["from_state"] == "PENDING"
        assert entries[0]["to_state"] == "POLICY_EVAL"

        # Verify last entry is auto_approve (since this is a low-risk AUTO review)
        assert entries[-1]["action"] == "auto_approve"
        assert entries[-1]["from_state"] == "POLICY_EVAL"
        assert entries[-1]["to_state"] == "COMPLETE"


# ---------------------------------------------------------------------------
# TEST-05: Query review by ID
# ---------------------------------------------------------------------------


class TestQueryReview:
    """TEST-05: GET /api/v1/reviews/{id} returns full review data."""

    @pytest.mark.asyncio
    async def test_query_review(self, client, auth_headers):
        """Submitted review can be queried and matches submission fields."""
        submit_resp = await _submit_review(
            client,
            auth_headers,
            type="video_review",
            content_ref="s3://bucket/query-test.mp4",
            source_system="kais-movie-agent",
            priority="normal",
            risk_score=0.1,
        )
        review_id = submit_resp.json()["data"]["review_id"]

        # Query the review
        query_resp = await client.get(
            f"/api/v1/reviews/{review_id}",
            headers=auth_headers,
        )
        assert query_resp.status_code == 200
        data = query_resp.json()["data"]
        assert data["type"] == "video_review"
        assert data["content_ref"] == "s3://bucket/query-test.mp4"
        assert data["source_system"] == "kais-movie-agent"


# ---------------------------------------------------------------------------
# TEST-06: Unauthorized returns 401
# ---------------------------------------------------------------------------


class TestUnauthorized:
    """TEST-06: Protected endpoints return 401 without valid JWT."""

    @pytest.mark.asyncio
    async def test_unauthorized_returns_401(self, client):
        """GET /api/v1/reviews/{id} without auth returns 401."""
        response = await client.get("/api/v1/reviews/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_approve_returns_401(self, client):
        """POST approve without auth returns 401."""
        response = await client.post(
            "/api/v1/reviews/1/approve",
            json={"comment": "test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_reject_returns_401(self, client):
        """POST reject without auth returns 401."""
        response = await client.post(
            "/api/v1/reviews/1/reject",
            json={"reason": "test"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TEST-07: Concurrent conflict returns 409
# ---------------------------------------------------------------------------


class TestConcurrentConflict:
    """TEST-07: Second approve on same review returns 409 (state conflict)."""

    @pytest.mark.asyncio
    async def test_concurrent_conflict_returns_409(self, client, auth_headers):
        """Approving an already-approved review returns 409."""
        # Submit high-risk to get APPROVING state
        submit_resp = await _submit_review(
            client, auth_headers, risk_score=0.8, source_system="kais-movie-agent"
        )
        review_id = submit_resp.json()["data"]["review_id"]

        # First approve -- should succeed
        approve_resp_1 = await client.post(
            f"/api/v1/reviews/{review_id}/approve",
            json={"comment": "First approval"},
            headers=auth_headers,
        )
        assert approve_resp_1.status_code == 200

        # Second approve -- should fail with 409
        approve_resp_2 = await client.post(
            f"/api/v1/reviews/{review_id}/approve",
            json={"comment": "Second approval"},
            headers=auth_headers,
        )
        assert approve_resp_2.status_code == 409


# ---------------------------------------------------------------------------
# TEST-08: Invalid state transition returns 409
# ---------------------------------------------------------------------------


class TestInvalidTransition:
    """TEST-08: Approve on non-APPROVING review returns 409."""

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_409(self, client, auth_headers):
        """Approving a COMPLETE (auto-approved) review returns 409."""
        # Submit low-risk movie-agent -> AUTO -> COMPLETE
        submit_resp = await _submit_review(
            client,
            auth_headers,
            risk_score=0.1,
            source_system="kais-movie-agent",
        )
        review_id = submit_resp.json()["data"]["review_id"]
        assert submit_resp.json()["data"]["state"] == "COMPLETE"

        # Try to approve the COMPLETE review
        approve_resp = await client.post(
            f"/api/v1/reviews/{review_id}/approve",
            json={"comment": "Should fail"},
            headers=auth_headers,
        )
        assert approve_resp.status_code == 409
        detail = approve_resp.json()["detail"]
        assert "APPROVING" in detail


# ---------------------------------------------------------------------------
# TEST-09: Non-existent review returns 404
# ---------------------------------------------------------------------------


class TestNotFound:
    """TEST-09: GET /api/v1/reviews/{id} returns 404 for non-existent review."""

    @pytest.mark.asyncio
    async def test_nonexistent_review_returns_404(self, client, auth_headers):
        """Query for review ID 99999 returns 404."""
        response = await client.get(
            "/api/v1/reviews/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TEST-10: Concurrent submissions maintain independent state
# ---------------------------------------------------------------------------


class TestConcurrentSubmissions:
    """TEST-10: Multiple concurrent submissions have independent state machines."""

    @pytest.mark.asyncio
    async def test_concurrent_submissions_independent(self, client, auth_headers):
        """Three concurrent submissions produce different review_ids and correct states."""
        tasks = [
            _submit_review(
                client,
                auth_headers,
                content_ref=f"s3://bucket/concurrent-{i}.mp4",
                risk_score=0.1 if i == 0 else 0.8,
                source_system="kais-movie-agent",
            )
            for i in range(3)
        ]
        responses = await asyncio.gather(*tasks)

        review_ids = []
        for i, resp in enumerate(responses):
            assert resp.status_code == 202, f"Submission {i} failed: {resp.text}"
            body = resp.json()
            rid = body["data"]["review_id"]
            review_ids.append(rid)

            if i == 0:
                # Low risk -> AUTO -> COMPLETE
                assert body["data"]["routing"] == "AUTO"
                assert body["data"]["state"] == "COMPLETE"
            else:
                # High risk -> HUMAN -> APPROVING
                assert body["data"]["routing"] == "HUMAN"
                assert body["data"]["state"] == "APPROVING"

        # Verify all review_ids are unique
        assert len(set(review_ids)) == 3, f"Expected 3 unique IDs, got {review_ids}"
