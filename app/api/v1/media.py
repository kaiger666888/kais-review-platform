"""Media URL generation endpoints for video streaming and image access.

GET /api/v1/media/{shot_card_id}/video  -- Generate MinIO presigned URL for video
GET /api/v1/media/{shot_card_id}/image  -- Generate MinIO presigned URL for keyframe image
"""

from datetime import timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.shot_card import ShotCard

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/media", tags=["media"])


def _get_minio_client():
    """Create MinIO client from settings. Returns None if not configured."""
    try:
        from minio import MinIO
    except ImportError:
        logger.warning("minio_package_not_installed")
        return None

    settings = get_settings()
    if not settings.minio_access_key or not settings.minio_secret_key:
        return None
    return MinIO(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


@router.get("/{shot_card_id}/video")
async def get_video_url(
    shot_card_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate a presigned URL for video streaming.

    Falls back to direct URL if MinIO is not configured.
    """
    shot_card = await db.get(ShotCard, shot_card_id)
    if not shot_card or not shot_card.visual_bundle:
        raise HTTPException(status_code=404, detail="Shot card or visual bundle not found")

    video_clip = shot_card.visual_bundle.get("video_clip")
    if not video_clip:
        raise HTTPException(status_code=404, detail="No video clip available")

    video_url = video_clip.get("url")
    if not video_url:
        raise HTTPException(status_code=404, detail="Video URL not found in bundle")

    client = _get_minio_client()
    if client:
        try:
            settings = get_settings()
            presigned = client.presigned_get_object(
                bucket_name=settings.minio_bucket,
                object_name=video_url,
                expires=timedelta(hours=1),
            )
            return {"url": presigned, "duration": video_clip.get("duration", 0)}
        except Exception as e:
            logger.warning("minio_presign_failed", error=str(e), shot_card_id=shot_card_id)
            # Fall back to direct URL

    # Direct URL fallback (works if video URLs are already accessible)
    return {"url": video_url, "duration": video_clip.get("duration", 0)}


@router.get("/{shot_card_id}/image")
async def get_image_url(
    shot_card_id: int,
    frame: str = "first",  # "first" or "last"
    candidate: int | None = None,  # candidate index
    db: AsyncSession = Depends(get_db),
):
    """Generate a presigned URL for a keyframe image.

    Args:
        frame: "first" or "last" keyframe.
        candidate: Optional candidate index (0-based) to get that candidate's keyframe.
    """
    shot_card = await db.get(ShotCard, shot_card_id)
    if not shot_card or not shot_card.visual_bundle:
        raise HTTPException(status_code=404, detail="Shot card or visual bundle not found")

    bundle = shot_card.visual_bundle

    if candidate is not None:
        candidates = bundle.get("candidates", [])
        if candidate >= len(candidates):
            raise HTTPException(status_code=404, detail=f"Candidate {candidate} not found")
        cand = candidates[candidate]
        keyframes = cand.get("keyframes", {})
    else:
        keyframes = bundle.get("keyframes", {})

    kf = keyframes.get(frame)
    if not kf:
        raise HTTPException(status_code=404, detail=f"{frame} keyframe not found")

    image_url = kf.get("url")
    if not image_url:
        raise HTTPException(status_code=404, detail="Image URL not found")

    client = _get_minio_client()
    if client:
        try:
            settings = get_settings()
            presigned = client.presigned_get_object(
                bucket_name=settings.minio_bucket,
                object_name=image_url,
                expires=timedelta(hours=1),
            )
            return {"url": presigned}
        except Exception as e:
            logger.warning("minio_presign_failed", error=str(e))

    return {"url": image_url}
