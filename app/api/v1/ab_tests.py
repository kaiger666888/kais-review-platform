"""A/B test batch creation and query API endpoints.

POST /api/v1/ab-tests/    -- Create A/B test batch with shot_ids
GET  /api/v1/ab-tests/{batch_id} -- Query A/B test pairs by batch_id
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.ab_test_pair import ABTestPair
from app.models.schemas import (
    ABTestCreateRequest,
    ABTestCreateResponse,
    ABTestPairResponse,
    ApiResponse,
)

router = APIRouter(prefix="/api/v1/ab-tests", tags=["ab-tests"])


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ABTestCreateResponse],
)
async def create_ab_test_batch(
    request: ABTestCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create an A/B test batch with a UUID batch_id for each shot_id."""
    batch_id = str(uuid.uuid4())

    for shot_id in request.shot_ids:
        pair = ABTestPair(
            batch_id=batch_id,
            shot_id=shot_id,
        )
        db.add(pair)

    await db.commit()

    return ApiResponse(
        data=ABTestCreateResponse(
            batch_id=batch_id,
            total=len(request.shot_ids),
        ).model_dump()
    )


@router.get(
    "/{batch_id}",
    response_model=ApiResponse[list[ABTestPairResponse]],
)
async def get_ab_test_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Query A/B test pairs by batch_id."""
    result = await db.execute(
        select(ABTestPair).where(ABTestPair.batch_id == batch_id)
    )
    pairs = result.scalars().all()

    pair_responses = [
        ABTestPairResponse(
            id=p.id,
            batch_id=p.batch_id,
            shot_id=p.shot_id,
            ai_score=p.ai_score,
            human_decision=p.human_decision,
            created_at=p.created_at,
        ).model_dump()
        for p in pairs
    ]

    return ApiResponse(data=pair_responses)
