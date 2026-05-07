"""Async client for submitting GPU task reviews to the review platform.

Gold-team imports this module to submit GPU tasks for review before
dispatch. AUTO-approved reviews return immediately; HUMAN-routed reviews
require waiting for callback approval.

Usage:
    client = ReviewPlatformClient()
    result = await client.submit_gpu_review(
        task_id="uuid-xxx",
        task_type="blender_render",
        created_by="telegram",
        metadata={"gpu_required": True, "params": {...}},
        callback_url="http://192.168.71.140:8900/callback/review_result",
        callback_secret="shared-secret",
    )
    if result.routing == "AUTO":
        # Proceed immediately
    else:
        # Wait for callback
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

# ---------------------------------------------------------------------------
# Risk-tier type sets (GT-03: engine -> risk_tier mapping)
# ---------------------------------------------------------------------------

HIGH_RISK_TYPES: frozenset[str] = frozenset(
    {
        "blender_render",
        "custom_script",
        "face_swap",
        "face_enhance",
        "frame_enhance",
        "lip_sync_ff",
        "colorize",
        "age_modify",
        "face_edit",
        "bg_remove",
        "face_pipeline",
    }
)

LOW_RISK_TYPES: frozenset[str] = frozenset(
    {
        "tts_generation",
        "sfx_generation",
        "vfx_audio_generation",
        "music_generation",
        "music_cover",
        "music_remix",
        "music_repaint",
        "music_extract",
    }
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ReviewSubmitResult:
    """Result of a review submission."""

    review_id: int
    state: str
    routing: str | None  # "AUTO", "HUMAN", "AI_AUDIT", "BLOCK"


@dataclass
class ReviewQueryResult:
    """Result of a review status query."""

    review_id: int
    state: str
    disposition: str | None
    version: int


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ReviewClientError(Exception):
    """Base exception for review client errors."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ReviewPlatformClient:
    """Async client for submitting GPU task reviews to the review platform.

    Authenticates via API key exchange for JWT, then submits reviews
    with gold-team metadata including task_type, GPU requirements,
    and requesting user information.
    """

    def __init__(
        self,
        base_url: str = "http://192.168.71.140:8090",
        api_key: str = "",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._http_client = httpx.AsyncClient(timeout=timeout)
        self._token: str | None = None
        self._token_expires: float = 0.0

    # -- Risk score computation (GT-03) --

    def _compute_risk_score(self, task_type: str) -> float:
        """Compute risk score from task type.

        High-risk types (blender/facefusion): 0.8
        Low-risk types (tts/woosh/acestep): 0.2
        Unknown types: 0.5 (medium, defaults to HUMAN by policy)
        """
        if task_type in HIGH_RISK_TYPES:
            return 0.8
        elif task_type in LOW_RISK_TYPES:
            return 0.2
        return 0.5

    # -- Authentication --

    async def _ensure_token(self) -> str:
        """Ensure a valid JWT token is available, refreshing if needed."""
        if self._token and time.time() < self._token_expires:
            return self._token

        resp = await self._http_client.post(
            f"{self._base_url}/api/v1/auth/token",
            json={
                "api_key": self._api_key,
                "client_id": "kais-gold-team",
            },
        )
        if resp.status_code != 200:
            raise ReviewClientError(
                f"Authentication failed: {resp.status_code} {resp.text}"
            )

        data = resp.json()["data"]
        self._token = data["access_token"]
        # Cache token with 60s safety margin before expiry
        expires_in = data.get("expires_in", 900)
        self._token_expires = time.time() + expires_in - 60
        return self._token

    # -- Public API --

    async def submit_gpu_review(
        self,
        task_id: str,
        task_type: str,
        created_by: str = "telegram",
        metadata: dict | None = None,
        callback_url: str | None = None,
        callback_secret: str | None = None,
        priority: str = "normal",
    ) -> ReviewSubmitResult:
        """Submit a GPU task for review.

        Maps gold-team task data to ReviewCreateRequest format:
        - type: "gpu_task"
        - content_ref: task_id (the gold-team task UUID)
        - source_system: "kais-gold-team"
        - metadata: {"task_type": task_type, "created_by": created_by, **metadata}
        - risk_score: computed from task_type (high=0.8, low=0.2, unknown=0.5)
        - callback_url and callback_secret passed through

        Per CONTEXT.md decisions (GT-01, GT-02):
        - Review submission includes task type, GPU requirements, requesting user
        - AUTO-approved reviews return immediately, gold-team continues without waiting
        """
        token = await self._ensure_token()

        # Build review metadata
        review_metadata: dict = {
            "task_type": task_type,
            "created_by": created_by,
        }
        if metadata:
            review_metadata.update(metadata)

        risk_score = self._compute_risk_score(task_type)

        body: dict = {
            "type": "gpu_task",
            "content_ref": task_id,
            "source_system": "kais-gold-team",
            "metadata": review_metadata,
            "priority": priority,
            "risk_score": risk_score,
        }
        if callback_url is not None:
            body["callback_url"] = callback_url
        if callback_secret is not None:
            body["callback_secret"] = callback_secret

        try:
            resp = await self._http_client.post(
                f"{self._base_url}/api/v1/reviews",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.ConnectError as exc:
            raise ReviewClientError(
                f"Connection error submitting review: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ReviewClientError(
                f"Timeout submitting review: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise ReviewClientError(
                f"Review submission failed: {resp.status_code} {resp.text}"
            )

        result_data = resp.json()["data"]
        return ReviewSubmitResult(
            review_id=result_data["review_id"],
            state=result_data["state"],
            routing=result_data.get("routing"),
        )

    async def query_review_status(self, review_id: int) -> ReviewQueryResult:
        """Query review status by review_id.

        Calls GET /api/v1/reviews/{review_id}.
        Returns ReviewQueryResult with state, disposition, version.
        """
        token = await self._ensure_token()

        try:
            resp = await self._http_client.get(
                f"{self._base_url}/api/v1/reviews/{review_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.ConnectError as exc:
            raise ReviewClientError(
                f"Connection error querying review: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ReviewClientError(
                f"Timeout querying review: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise ReviewClientError(
                f"Review query failed: {resp.status_code} {resp.text}"
            )

        result_data = resp.json()["data"]
        return ReviewQueryResult(
            review_id=result_data["id"],
            state=result_data["state"],
            disposition=result_data.get("disposition"),
            version=result_data["version"],
        )

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._http_client.aclose()
