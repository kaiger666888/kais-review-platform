"""Shot Card timeout manager: auto-reject and escalation cron for arq.

Provides check_shot_card_timeouts as an arq-compatible cron function that:
- Auto-rejects HUMAN-routed ShotCards awaiting_audit for >24h
- Escalates AI_AUDIT-routed ShotCards awaiting_audit for >5min to HUMAN

Does NOT import from app.workers.tasks.py to avoid circular imports.
Dependencies (DB session, router) are created internally.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import structlog
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.shot_card import ShotCard, AuditStatus

logger = structlog.get_logger(__name__)

# Timeout configuration per routing decision
TIMEOUT_CONFIG: dict[str, dict] = {
    "HUMAN": {
        "timeout_seconds": 86400,  # 24 hours
        "action": "reject",
    },
    "AI_AUDIT": {
        "timeout_seconds": 300,  # 5 minutes
        "action": "escalate",
    },
}


@dataclass
class ShotCardTimeoutSettings:
    """Wraps timeout configuration for testability.

    Attributes:
        config: Mapping of routing decision to timeout config dict.
    """

    config: dict[str, dict] = field(default_factory=lambda: TIMEOUT_CONFIG)

    def get_timeout(self, routing_decision: str) -> int | None:
        """Get timeout seconds for a routing decision."""
        entry = self.config.get(routing_decision)
        return entry["timeout_seconds"] if entry else None

    def get_action(self, routing_decision: str) -> str | None:
        """Get timeout action for a routing decision."""
        entry = self.config.get(routing_decision)
        return entry["action"] if entry else None


async def create_audit_entry(
    session,
    shot_card,
    action: str,
    actor: str,
    from_state: str | None = None,
    to_state: str | None = None,
    payload: dict | None = None,
) -> None:
    """Create an AuditEntry for a timeout action.

    Uses the same hash chain pattern as the main state machine.
    This is a simplified version for timeout operations.

    Args:
        session: Async database session.
        shot_card: ShotCard ORM object (used for shot_card_id).
        action: Action string (e.g. "timeout_rejected", "timeout_escalated").
        actor: Who performed the action (e.g. "timeout").
        from_state: Previous state.
        to_state: New state.
        payload: Additional data.
    """
    import hashlib
    import json

    from app.models.audit_entry import AuditEntry

    # Compute hash chain (simplified - uses own_hash only for timeout entries)
    payload_str = json.dumps(payload or {}, default=str, sort_keys=True)
    hash_input = f"{shot_card.id}:{action}:{actor}:{payload_str}"
    own_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    entry = AuditEntry(
        shot_card_id=shot_card.id,
        action=action,
        actor=actor,
        from_state=from_state,
        to_state=to_state,
        payload=payload,
        prev_hash="timeout",  # Timeout entries start their own chain
        own_hash=own_hash,
    )
    session.add(entry)


async def check_shot_card_timeouts(ctx: dict) -> list[str]:
    """Scan for ShotCards that have exceeded timeout thresholds.

    This function is designed to be called as an arq cron job.
    It creates its own DB session and ApprovalRouter internally
    to avoid circular imports with app.workers.tasks.

    Args:
        ctx: arq context dict (unused, dependencies created internally).

    Returns:
        List of shot_ids that were acted on (rejected or escalated).
    """
    timeout_settings = ShotCardTimeoutSettings()
    affected: list[str] = []

    async with async_session_factory() as session:
        # Query all awaiting_audit ShotCards with a routing decision
        query = select(ShotCard).where(
            ShotCard.audit_status == AuditStatus.AWAITING_AUDIT,
            ShotCard.routing_decision.isnot(None),
        )
        result = await session.execute(query)
        cards = result.scalars().all()

        now = datetime.now(timezone.utc)

        for card in cards:
            routing = card.routing_decision
            timeout_seconds = timeout_settings.get_timeout(routing)
            action = timeout_settings.get_action(routing)

            if timeout_seconds is None or action is None:
                continue

            # Compute elapsed time since last update
            updated_at = card.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            elapsed = (now - updated_at).total_seconds()

            if elapsed <= timeout_seconds:
                continue

            if action == "reject":
                # Auto-reject HUMAN cards past 24h
                try:
                    logger.info(
                        "shot_card_timeout_rejecting",
                        shot_id=card.shot_id,
                        routing_decision=routing,
                        elapsed_seconds=elapsed,
                        timeout_seconds=timeout_seconds,
                    )

                    # Update audit status to rejected
                    card.audit_status = AuditStatus.REJECTED

                    # Create audit entry
                    await create_audit_entry(
                        session,
                        card,
                        action="timeout_rejected",
                        actor="timeout",
                        from_state="awaiting_audit",
                        to_state="rejected",
                        payload={
                            "reason": "Exceeded 24h human review timeout",
                            "timeout_seconds": timeout_seconds,
                            "elapsed_seconds": elapsed,
                            "routing_decision": routing,
                        },
                    )

                    affected.append(card.shot_id)
                    logger.info(
                        "shot_card_timeout_rejected",
                        shot_id=card.shot_id,
                    )
                except Exception as e:
                    logger.error(
                        "shot_card_timeout_reject_failed",
                        shot_id=card.shot_id,
                        error=str(e),
                    )

            elif action == "escalate":
                # Escalate AI_AUDIT cards past 5min to HUMAN
                try:
                    logger.info(
                        "shot_card_timeout_escalating",
                        shot_id=card.shot_id,
                        routing_decision=routing,
                        elapsed_seconds=elapsed,
                        timeout_seconds=timeout_seconds,
                    )

                    # Update routing decision to HUMAN
                    card.routing_decision = "HUMAN"

                    # Create audit entry
                    await create_audit_entry(
                        session,
                        card,
                        action="timeout_escalated",
                        actor="timeout",
                        from_state="awaiting_audit",
                        to_state="awaiting_audit",
                        payload={
                            "reason": "AI audit timeout, escalating to human review",
                            "timeout_seconds": timeout_seconds,
                            "elapsed_seconds": elapsed,
                            "from_routing": "AI_AUDIT",
                            "to_routing": "HUMAN",
                        },
                    )

                    affected.append(card.shot_id)
                    logger.info(
                        "shot_card_timeout_escalated",
                        shot_id=card.shot_id,
                        new_routing="HUMAN",
                    )
                except Exception as e:
                    logger.error(
                        "shot_card_timeout_escalate_failed",
                        shot_id=card.shot_id,
                        error=str(e),
                    )

        if affected:
            await session.commit()

    return affected
