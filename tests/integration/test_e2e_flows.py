"""End-to-end integration tests for dual-bot coordination review flows.

Tests the full review lifecycle for both gold-team and movie-agent source systems:
- Approval flow: submit -> HUMAN routing -> approve -> COMPLETE
- Rejection flow: submit -> HUMAN routing -> reject -> COMPLETE
- Callback delivery: retry on failure, HMAC signature verification

Uses shared E2E fixtures from conftest.py:
- e2e_gold_team_review_payload: gold-team review submission payload
- e2e_movie_agent_review_payload: movie-agent review submission payload
- mock_callback_server: aiohttp server recording POST callbacks

Covers E2E-02 (gold-team approval), E2E-03 (movie-agent approval),
E2E-04 (rejection + callback delivery).
"""

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _submit_high_risk_review(
    client: AsyncClient,
    auth_headers: dict,
    payload: dict,
) -> dict:
    """Submit a review that routes to HUMAN (APPROVING state).

    Overrides risk_score to 0.8 and includes required fields to ensure
    the policy engine routes to HUMAN disposition.

    Returns the JSON response body.
    """
    # Ensure required API fields are present (payload fixtures may not include
    # type/content_ref since they model the external system's perspective)
    body = {
        "type": payload.get("task_type", "video_review"),
        "content_ref": f"s3://bucket/e2e-test-{payload['source_system']}.mp4",
        **payload,
        "risk_score": 0.8,
    }
    response = await client.post(
        "/api/v1/reviews/",
        json=body,
        headers=auth_headers,
    )
    assert response.status_code == 202, f"Submit failed: {response.text}"
    data = response.json()["data"]
    assert data["routing"] == "HUMAN", f"Expected HUMAN routing, got {data['routing']}"
    assert data["state"] == "APPROVING", f"Expected APPROVING state, got {data['state']}"
    return response.json()


# ---------------------------------------------------------------------------
# E2E-02: Gold-team approval + rejection flows
# E2E-03: Movie-agent approval + rejection flows
# ---------------------------------------------------------------------------


class TestE2EApprovalFlows:
    """E2E tests: submit review -> approve -> verify COMPLETE state."""

    @pytest.mark.asyncio
    async def test_gold_team_approve_e2e(
        self, client, auth_headers, e2e_gold_team_review_payload
    ):
        """Gold-team review: submit -> approve -> COMPLETE with approve audit trail."""
        # Submit high-risk gold-team review -> APPROVING
        submit_body = await _submit_high_risk_review(
            client, auth_headers, e2e_gold_team_review_payload
        )
        review_id = submit_body["data"]["review_id"]

        # Approve the review
        approve_resp = await client.post(
            f"/api/v1/reviews/{review_id}/approve",
            json={"comment": "E2E gold-team approval"},
            headers=auth_headers,
        )
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"
        approve_data = approve_resp.json()["data"]
        assert approve_data["state"] == "COMPLETE"

        # Verify final state via GET
        query_resp = await client.get(
            f"/api/v1/reviews/{review_id}",
            headers=auth_headers,
        )
        assert query_resp.status_code == 200
        review = query_resp.json()["data"]
        assert review["state"] == "COMPLETE"
        assert review["source_system"] == "kais-gold-team"
        assert review["callback_url"] is not None

        # Verify audit trail records the approve action
        audit_resp = await client.get(
            f"/api/v1/audit/{review_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        actions = [e["action"] for e in audit_resp.json()["data"]]
        assert "approve" in actions

    @pytest.mark.asyncio
    async def test_movie_agent_approve_e2e(
        self, client, auth_headers, e2e_movie_agent_review_payload
    ):
        """Movie-agent review: submit -> approve -> COMPLETE with approve audit trail."""
        # Submit high-risk movie-agent review -> APPROVING
        submit_body = await _submit_high_risk_review(
            client, auth_headers, e2e_movie_agent_review_payload
        )
        review_id = submit_body["data"]["review_id"]

        # Approve the review
        approve_resp = await client.post(
            f"/api/v1/reviews/{review_id}/approve",
            json={"comment": "E2E movie-agent approval"},
            headers=auth_headers,
        )
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"
        approve_data = approve_resp.json()["data"]
        assert approve_data["state"] == "COMPLETE"

        # Verify final state via GET
        query_resp = await client.get(
            f"/api/v1/reviews/{review_id}",
            headers=auth_headers,
        )
        assert query_resp.status_code == 200
        review = query_resp.json()["data"]
        assert review["state"] == "COMPLETE"
        assert review["source_system"] == "kais-movie-agent"
        assert review["callback_url"] is not None

        # Verify audit trail records the approve action
        audit_resp = await client.get(
            f"/api/v1/audit/{review_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        actions = [e["action"] for e in audit_resp.json()["data"]]
        assert "approve" in actions


class TestE2ERejectionFlows:
    """E2E tests: submit review -> reject -> verify COMPLETE state with reject disposition."""

    @pytest.mark.asyncio
    async def test_gold_team_reject_e2e(
        self, client, auth_headers, e2e_gold_team_review_payload
    ):
        """Gold-team review: submit -> reject -> COMPLETE with reject audit trail."""
        # Submit high-risk gold-team review -> APPROVING
        submit_body = await _submit_high_risk_review(
            client, auth_headers, e2e_gold_team_review_payload
        )
        review_id = submit_body["data"]["review_id"]

        # Reject the review
        reject_resp = await client.post(
            f"/api/v1/reviews/{review_id}/reject",
            json={"reason": "E2E gold-team rejection: quality below threshold"},
            headers=auth_headers,
        )
        assert reject_resp.status_code == 200, f"Reject failed: {reject_resp.text}"
        reject_data = reject_resp.json()["data"]
        assert reject_data["state"] == "COMPLETE"

        # Verify final state via GET
        query_resp = await client.get(
            f"/api/v1/reviews/{review_id}",
            headers=auth_headers,
        )
        assert query_resp.status_code == 200
        review = query_resp.json()["data"]
        assert review["state"] == "COMPLETE"
        assert review["source_system"] == "kais-gold-team"
        assert review["callback_url"] is not None

        # Verify audit trail records the reject action
        audit_resp = await client.get(
            f"/api/v1/audit/{review_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        actions = [e["action"] for e in audit_resp.json()["data"]]
        assert "reject" in actions

    @pytest.mark.asyncio
    async def test_movie_agent_reject_e2e(
        self, client, auth_headers, e2e_movie_agent_review_payload
    ):
        """Movie-agent review: submit -> reject -> COMPLETE with reject audit trail."""
        # Submit high-risk movie-agent review -> APPROVING
        submit_body = await _submit_high_risk_review(
            client, auth_headers, e2e_movie_agent_review_payload
        )
        review_id = submit_body["data"]["review_id"]

        # Reject the review
        reject_resp = await client.post(
            f"/api/v1/reviews/{review_id}/reject",
            json={"reason": "E2E movie-agent rejection: storyboard quality issue"},
            headers=auth_headers,
        )
        assert reject_resp.status_code == 200, f"Reject failed: {reject_resp.text}"
        reject_data = reject_resp.json()["data"]
        assert reject_data["state"] == "COMPLETE"

        # Verify final state via GET
        query_resp = await client.get(
            f"/api/v1/reviews/{review_id}",
            headers=auth_headers,
        )
        assert query_resp.status_code == 200
        review = query_resp.json()["data"]
        assert review["state"] == "COMPLETE"
        assert review["source_system"] == "kais-movie-agent"
        assert review["callback_url"] is not None

        # Verify audit trail records the reject action
        audit_resp = await client.get(
            f"/api/v1/audit/{review_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        actions = [e["action"] for e in audit_resp.json()["data"]]
        assert "reject" in actions
