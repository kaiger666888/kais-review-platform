"""Shot Card Aggregator -- orchestrates the aggregation pipeline.

Top-level service that coordinates topology collapsing, progressive fill,
policy evaluation, and event emission for node completion events. Single
entry point for all OpenClaw node completion processing.

Pipeline: node_completed event -> topology collapse -> ensure Shot Card
          -> progressive fill -> check readiness -> policy evaluation
          -> provenance writeback -> emit events
"""

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory
from app.core.events import event_manager
from app.core.policy_v2 import ShotCardPolicyEngine
from app.models.audit_entry import AuditEntry
from app.models.shot_card import ShotCard
from app.services.git_policy_provider import GitPolicyProvider, get_git_policy_provider
from app.services.progressive_fill import ProgressiveFillEngine
from app.services.topology_collapser import TopologyCollapser

logger = structlog.get_logger(__name__)


class ShotCardAggregator:
    """Orchestrates the aggregation pipeline for node completion events.

    Pipeline: node_completed event -> topology collapse -> progressive fill
              -> min_audit_set check -> policy evaluation -> provenance
              writeback -> event emission
    """

    def __init__(self) -> None:
        self.collapser = TopologyCollapser()
        self.filler = ProgressiveFillEngine()
        self.policy_engine = ShotCardPolicyEngine()
        self.git_provider: GitPolicyProvider | None = None

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

        # Step 4.5: Policy evaluation when ready and not yet evaluated
        policy_result_dict = None
        if min_audit_satisfied and shot_card.routing_decision is None:
            policy_result_dict = await self._evaluate_policy(shot_card)
            shot_card = await self._write_provenance(shot_card, policy_result_dict)
            await self._create_audit_entry(shot_card, policy_result_dict)

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
            "policy_result": policy_result_dict,
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

    # -- Git Provider -------------------------------------------------------

    def _get_git_provider(self) -> GitPolicyProvider:
        """Lazy-initialize and return the GitPolicyProvider singleton."""
        if self.git_provider is None:
            self.git_provider = get_git_policy_provider()
        return self.git_provider

    # -- Policy Evaluation ---------------------------------------------------

    async def _evaluate_policy(self, shot_card: ShotCard) -> dict:
        """Evaluate policy for a ShotCard using Git-backed policies.

        Fetches policies from the Git provider, loads them into the engine,
        and evaluates the ShotCard against the stacked layers.

        Args:
            shot_card: The ShotCard to evaluate.

        Returns:
            Dict with "result" (PolicyResult) and "commit_sha" (str).
        """
        git_provider = self._get_git_provider()
        all_policies, commit_sha = await git_provider.get_policies()

        # Load policies into engine by layer
        policies_by_layer: dict[str, list[str]] = {}

        # Global layer
        if "global" in all_policies:
            for filename, policy_dict in all_policies["global"].items():
                name = policy_dict.get("name", filename)
                self.policy_engine._policies[name] = policy_dict
                policies_by_layer.setdefault("global", []).append(name)

        # Project-specific layer
        if "projects" in all_policies and shot_card.project_id in all_policies["projects"]:
            project_layer = all_policies["projects"][shot_card.project_id]
            for filename, policy_dict in project_layer.items():
                name = policy_dict.get("name", filename)
                self.policy_engine._policies[name] = policy_dict
                policies_by_layer.setdefault("project", []).append(name)

        # Temporary layer
        if "temporary" in all_policies:
            for filename, policy_dict in all_policies["temporary"].items():
                name = policy_dict.get("name", filename)
                self.policy_engine._policies[name] = policy_dict
                policies_by_layer.setdefault("temporary", []).append(name)

        # Local fallback
        if "local" in all_policies:
            for i, policy_dict in enumerate(all_policies["local"]):
                name = policy_dict.get("name", f"local_{i}")
                self.policy_engine._policies[name] = policy_dict
                policies_by_layer.setdefault("global", []).append(name)

        # Evaluate with stack
        result = self.policy_engine.evaluate_with_stack(
            shot_card, policies_by_layer, policy_commit_sha=commit_sha
        )

        return {"result": result, "commit_sha": commit_sha}

    # -- Provenance Writeback ------------------------------------------------

    async def _write_provenance(self, shot_card: ShotCard, policy_result_dict: dict) -> ShotCard:
        """Write routing_decision and policy_commit_sha back to the ShotCard.

        Args:
            shot_card: The ShotCard to update.
            policy_result_dict: Dict with "result" (PolicyResult) and "commit_sha".

        Returns:
            Updated ShotCard instance.
        """
        from sqlalchemy.orm.attributes import flag_modified

        async with async_session_factory() as session:
            result = await session.execute(
                select(ShotCard).where(ShotCard.shot_id == shot_card.shot_id)
            )
            db_card = result.scalar_one_or_none()

            if db_card is not None:
                db_card.routing_decision = policy_result_dict["result"].disposition.value
                db_card.policy_commit_sha = policy_result_dict["commit_sha"]
                flag_modified(db_card, "routing_decision")
                await session.commit()
                await session.refresh(db_card)
                return db_card

            # Fallback: return original if not found in DB
            return shot_card

    # -- Audit Entry ---------------------------------------------------------

    async def _create_audit_entry(self, shot_card: ShotCard, policy_result_dict: dict) -> None:
        """Create an AuditEntry recording the policy evaluation.

        Args:
            shot_card: The ShotCard that was evaluated.
            policy_result_dict: Dict with "result" (PolicyResult) and "commit_sha".
        """
        policy_result = policy_result_dict["result"]
        entry = AuditEntry(
            shot_card_id=shot_card.id,
            action="policy_evaluated",
            actor="system:policy_engine",
            from_state="awaiting_audit",
            to_state=policy_result.disposition.value,
            payload={
                "matched_rule": policy_result.matched_rule,
                "policy_commit_sha": policy_result_dict["commit_sha"],
                "stack_layers": policy_result.stack_layers_evaluated,
            },
            prev_hash="0" * 64,
            own_hash="pending",
        )

        async with async_session_factory() as session:
            session.add(entry)
            await session.commit()
