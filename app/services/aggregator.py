"""Shot Card Aggregator -- orchestrates the aggregation pipeline.

Top-level service that coordinates topology collapsing, progressive fill,
and event emission for node completion events. Single entry point for all
OpenClaw node completion processing.

Pipeline: node_completed event -> topology collapse -> ensure Shot Card
          -> progressive fill -> check readiness -> emit events
"""

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory
from app.core.events import event_manager
from app.models.shot_card import ShotCard
from app.services.progressive_fill import ProgressiveFillEngine
from app.services.topology_collapser import TopologyCollapser

logger = structlog.get_logger(__name__)


class ShotCardAggregator:
    """Orchestrates the aggregation pipeline for node completion events.

    Pipeline: node_completed event -> topology collapse -> progressive fill
              -> min_audit_set check -> event emission
    """

    def __init__(self) -> None:
        self.collapser = TopologyCollapser()
        self.filler = ProgressiveFillEngine()

    async def handle_node_completion(self, event: dict) -> dict:
        """Process a node completion event through the full pipeline.

        Steps:
        1. Collapse node output to Shot Card bundle structure
        2. Ensure Shot Card exists (create if first node for this shot_id)
        3. Progressive fill the target JSONB column
        4. Check min_audit_set readiness
        5. Emit events (bundle_ready, shot_card_updated)

        Args:
            event: Dict with keys: execution_id, shot_id, project_id,
                node_type, node_output, optional narrative_context,
                optional provenance.

        Returns:
            Summary dict with processing result.
        """
        shot_id = event["shot_id"]
        node_type = event["node_type"]

        # Step 1: Collapse topology
        collapse_result = self.collapser.collapse(node_type, event["node_output"])
        target_column = collapse_result["target_column"]
        merge_data = collapse_result["merge_data"]

        # Step 2: Ensure Shot Card exists
        shot_card = await self._ensure_shot_card(event)
        if shot_card is None:
            logger.error("aggregator_failed_create", shot_id=shot_id)
            return {"status": "error", "reason": "failed_to_create_shot_card"}

        # Step 3: Progressive fill
        shot_card = await self.filler.fill(shot_id, target_column, merge_data)
        if shot_card is None:
            return {"status": "error", "reason": "fill_failed"}

        # Step 4: Check readiness
        min_audit_satisfied = self.filler.check_min_audit_set(shot_card)
        bundle_complete = self.filler.check_bundle_complete(shot_card, target_column)

        # Step 5: Emit events
        await self._emit_events(
            shot_card=shot_card,
            target_column=target_column,
            bundle_complete=bundle_complete,
            min_audit_satisfied=min_audit_satisfied,
        )

        return {
            "status": "ok",
            "shot_card_id": shot_card.id,
            "shot_id": shot_id,
            "updated_column": target_column,
            "bundle_complete": bundle_complete,
            "min_audit_satisfied": min_audit_satisfied,
        }

    async def _ensure_shot_card(self, event: dict) -> ShotCard | None:
        """Get or create Shot Card for this shot_id.

        Handles concurrent creation race condition via IntegrityError
        catch on the shot_id unique constraint.

        Args:
            event: Dict with shot_id, project_id, optional narrative_context,
                optional provenance, optional execution_id.

        Returns:
            Existing or newly created ShotCard, or None on failure.
        """
        shot_id = event["shot_id"]
        project_id = event["project_id"]

        async with async_session_factory() as session:
            result = await session.execute(
                select(ShotCard).where(ShotCard.shot_id == shot_id)
            )
            shot_card = result.scalar_one_or_none()

            if shot_card is not None:
                return shot_card

            # Create new Shot Card
            shot_card = ShotCard(
                shot_id=shot_id,
                project_id=project_id,
                narrative_context=event.get("narrative_context", {}),
                min_audit_set=["visual_bundle"],  # Default min audit set
                workflow_version=event.get("provenance", {}).get("workflow_version"),
                policy_commit_sha=event.get("provenance", {}).get("policy_commit_sha"),
                execution_id=event.get("execution_id"),
            )
            session.add(shot_card)

            try:
                await session.commit()
                await session.refresh(shot_card)
                logger.info(
                    "shot_card_created",
                    shot_id=shot_id,
                    project_id=project_id,
                )
                return shot_card
            except IntegrityError:
                # Concurrent creation race -- another event created it first
                await session.rollback()
                result = await session.execute(
                    select(ShotCard).where(ShotCard.shot_id == shot_id)
                )
                shot_card = result.scalar_one_or_none()
                if shot_card is not None:
                    logger.info(
                        "shot_card_race_resolved",
                        shot_id=shot_id,
                    )
                return shot_card

    async def _emit_events(
        self,
        shot_card: ShotCard,
        target_column: str,
        bundle_complete: bool,
        min_audit_satisfied: bool,
    ) -> None:
        """Emit progressive fill events to SSE clients.

        Always broadcasts shot_card_updated. If the bundle is complete,
        also broadcasts bundle_ready. Logs when min_audit_set is satisfied.

        Args:
            shot_card: The updated ShotCard instance.
            target_column: Which JSONB column was updated.
            bundle_complete: Whether the bundle is fully populated.
            min_audit_satisfied: Whether all required bundles are ready.
        """
        # Always emit shot_card_updated
        update_event = {
            "event_type": "shot_card_updated",
            "shot_id": shot_card.shot_id,
            "project_id": shot_card.project_id,
            "shot_card_id": shot_card.id,
            "updated_fields": [target_column],
            "min_audit_set_satisfied": min_audit_satisfied,
            "audit_status": shot_card.audit_status,
        }
        await event_manager.broadcast(update_event)

        # Emit bundle_ready when a bundle becomes complete
        if bundle_complete:
            bundle_event = {
                "event_type": "bundle_ready",
                "shot_id": shot_card.shot_id,
                "project_id": shot_card.project_id,
                "bundle_type": target_column,
                "shot_card_id": shot_card.id,
            }
            await event_manager.broadcast(bundle_event)

        # Log readiness transition
        if min_audit_satisfied:
            logger.info(
                "min_audit_set_satisfied",
                shot_id=shot_card.shot_id,
                shot_card_id=shot_card.id,
                bundles_complete=target_column,
            )
