"""Progressive Fill Engine -- incrementally fills Shot Card JSONB fields.

Merges node output data into existing Shot Card JSONB columns using deep
merge, handles order-agnostic completion (video before keyframes, etc.),
and provides readiness checks for min_audit_set and bundle completeness.

CRITICAL: Always calls flag_modified() on JSONB mutations so SQLAlchemy
detects the change and includes it in the next commit.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import async_session_factory
from app.models.shot_card import ShotCard

logger = structlog.get_logger(__name__)


class ProgressiveFillEngine:
    """Incrementally fills Shot Card JSONB fields as node outputs arrive.

    Handles order-agnostic merging: any field can arrive in any order.
    Uses deep merge to combine new data with existing partial data.
    """

    async def fill(
        self, shot_id: str, target_column: str, merge_data: dict
    ) -> ShotCard | None:
        """Merge data into a Shot Card JSONB column.

        Uses flag_modified() to ensure SQLAlchemy detects the mutation.

        Args:
            shot_id: The shot_id to look up.
            target_column: JSONB column name ("visual_bundle", "audio_bundle",
                or "narrative_context").
            merge_data: Dict to deep-merge into the column's current value.

        Returns:
            Updated ShotCard instance, or None if shot_id not found.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(ShotCard).where(ShotCard.shot_id == shot_id)
            )
            shot_card = result.scalar_one_or_none()

            if shot_card is None:
                # Cannot fill a non-existent card -- caller must create first
                return None

            # Get current value (may be None for nullable columns)
            current = getattr(shot_card, target_column)
            if current is None:
                current = {}

            # Deep merge new data into existing
            merged = self._deep_merge(current, merge_data)
            setattr(shot_card, target_column, merged)

            # CRITICAL: flag the column as modified for SQLAlchemy dirty tracking
            flag_modified(shot_card, target_column)

            await session.commit()
            await session.refresh(shot_card)

            logger.info(
                "progressive_fill",
                shot_id=shot_id,
                column=target_column,
                fields_updated=list(merge_data.keys()),
            )
            return shot_card

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base dict.

        - Dict values are merged recursively
        - Non-dict values in override replace base values
        - Order-agnostic: partial data accumulates correctly
        """
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ProgressiveFillEngine._deep_merge(
                    result[key], value
                )
            else:
                result[key] = value
        return result

    def check_min_audit_set(self, shot_card: ShotCard) -> bool:
        """Check if the Shot Card's min_audit_set is satisfied.

        min_audit_set is a list of bundle names that must be non-null
        and contain at least one key (meaningful data, not just non-null).

        Args:
            shot_card: The ShotCard to check.

        Returns:
            True only if ALL required bundles have meaningful data.
        """
        required = shot_card.min_audit_set or ["visual_bundle"]

        for bundle_name in required:
            bundle = getattr(shot_card, bundle_name, None)
            # A bundle is "satisfied" if it is non-None AND non-empty
            if bundle is None or not bundle:
                return False

        return True

    def check_bundle_complete(
        self, shot_card: ShotCard, bundle_name: str
    ) -> bool:
        """Check if a specific bundle is fully populated.

        Args:
            shot_card: The ShotCard to check.
            bundle_name: "visual_bundle", "audio_bundle", or other.

        Returns:
            True if the bundle has all required fields.
        """
        bundle = getattr(shot_card, bundle_name, None)
        if bundle is None:
            return False

        if bundle_name == "visual_bundle":
            # Requires keyframes (with first) AND prompt present
            has_keyframes = (
                bundle.get("keyframes") is not None
                and bundle.get("keyframes", {}).get("first") is not None
            )
            has_prompt = bundle.get("prompt") is not None
            return has_keyframes and has_prompt

        if bundle_name == "audio_bundle":
            # Requires (bgm_prompt OR sfx_prompt) AND status != pending
            has_prompts = (
                bundle.get("bgm_prompt") is not None
                or bundle.get("sfx_prompt") is not None
            )
            status = bundle.get("status", "pending")
            return has_prompts and status != "pending"

        # Other bundles: non-empty is sufficient
        return bool(bundle)
