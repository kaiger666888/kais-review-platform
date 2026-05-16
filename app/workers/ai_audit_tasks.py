"""AI audit arq tasks: shadow mode scoring and feedback loop.

Phase 0 stubs:
- record_shadow_score: loads ShotCard, runs scoring bus, writes ShadowScore row
- write_feedback: logs structured feedback data (MinIO write deferred)
"""

import structlog

from app.core.database import async_session_factory
from app.models.shadow_score import ShadowScore
from app.models.shot_card import ShotCard
from app.services.scoring_bus import get_scoring_bus

logger = structlog.get_logger(__name__)


async def record_shadow_score(ctx: dict, shot_card_id: int, human_decision: str) -> dict:
    """Load ShotCard, run scoring bus, write ShadowScore row.

    Args:
        ctx: arq context dict.
        shot_card_id: Primary key of the ShotCard.
        human_decision: The human reviewer's decision string.

    Returns:
        {"status": "recorded", "shot_card_id": id} on success.
        {"status": "error", "reason": "shot_card_not_found"} if ShotCard missing.
    """
    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)
        if shot_card is None:
            logger.warning(
                "shadow_score_shot_card_not_found",
                shot_card_id=shot_card_id,
            )
            return {"status": "error", "reason": "shot_card_not_found"}

        bus = get_scoring_bus()
        score_vectors = await bus.score(shot_card)

        for sv in score_vectors:
            shadow = ShadowScore(
                shot_card_id=shot_card_id,
                shot_id=shot_card.shot_id,
                score_vector=sv.model_dump(),
                human_decision=human_decision,
            )
            session.add(shadow)

        await session.commit()

        logger.info(
            "shadow_score_recorded",
            shot_card_id=shot_card_id,
            shot_id=shot_card.shot_id,
            vectors_count=len(score_vectors),
        )

        return {"status": "recorded", "shot_card_id": shot_card_id}


async def write_feedback(ctx: dict, shot_card_id: int, human_decision: str) -> dict:
    """Log structured feedback data for future MinIO archival.

    Phase 0 stub: logs feedback data via structlog without attempting
    MinIO connection. The feedback path schema is
    {bucket}/feedback/{date}/{project_id}.jsonl but MinIO write is
    deferred to a future phase.

    Args:
        ctx: arq context dict.
        shot_card_id: Primary key of the ShotCard.
        human_decision: The human reviewer's decision string.

    Returns:
        {"status": "logged"} indicating feedback was logged.
    """
    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)
        if shot_card is None:
            logger.warning(
                "feedback_shot_card_not_found",
                shot_card_id=shot_card_id,
            )
            return {"status": "logged"}

        logger.info(
            "feedback_data",
            shot_id=shot_card.shot_id,
            project_id=shot_card.project_id,
            human_decision=human_decision,
        )

    return {"status": "logged"}
