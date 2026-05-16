"""Tests for Shot Card timeout manager: auto-reject and escalation.

Verifies that:
- HUMAN-routed ShotCards awaiting_audit for >24h are auto-rejected
- AI_AUDIT-routed ShotCards awaiting_audit for >5min are escalated to desktop (HUMAN)
- AuditEntry is created for auto-rejected cards with actor="timeout"
- AuditEntry is created for escalated cards with action="timeout_escalated"
- ShotCards within timeout threshold are not affected
- Cron function returns list of affected shot_ids
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.shot_card import AuditStatus, RoutingDecision


def _make_shot_card(
    shot_id="shot-001",
    project_id="proj-001",
    routing_decision="HUMAN",
    audit_status="awaiting_audit",
    minutes_ago=0,
    execution_id="exec-001",
):
    """Create a mock ShotCard ORM object for testing."""
    card = MagicMock()
    card.shot_id = shot_id
    card.project_id = project_id
    card.execution_id = execution_id
    card.routing_decision = routing_decision
    card.audit_status = audit_status
    card.narrative_context = {"scene": "intro"}
    card.visual_bundle = {"keyframes": {}}
    card.audio_bundle = {"status": "pending"}
    card.updated_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    card.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return card


class TestHumanAutoReject:
    """Test HUMAN-routed cards are auto-rejected after 24h."""

    @pytest.mark.asyncio
    async def test_auto_reject_after_24h(self):
        """ShotCard in HUMAN review for >24h should be auto-rejected."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card = _make_shot_card(
            shot_id="shot-old",
            routing_decision="HUMAN",
            minutes_ago=25 * 60,  # 25 hours old
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_router = AsyncMock()
        mock_router.reject_single = AsyncMock(return_value=True)

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_shot_card_timeouts({})

            assert "shot-old" in result
            mock_router.reject_single.assert_called_once_with(
                "shot-old", "timeout", reason="Exceeded 24h human review timeout"
            )

    @pytest.mark.asyncio
    async def test_creates_audit_entry_on_reject(self):
        """Auto-rejection should create an AuditEntry with actor='timeout'."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card = _make_shot_card(
            shot_id="shot-reject",
            routing_decision="HUMAN",
            minutes_ago=25 * 60,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_router = AsyncMock()
        mock_router.reject_single = AsyncMock(return_value=True)

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ) as mock_audit:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await check_shot_card_timeouts({})

            mock_audit.assert_called()
            # Verify the call was for auto-reject
            call_kwargs = mock_audit.call_args
            assert call_kwargs[1].get("actor") == "timeout" or (
                len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "timeout"
            )


class TestAiAuditEscalate:
    """Test AI_AUDIT-routed cards are escalated after 5min."""

    @pytest.mark.asyncio
    async def test_escalate_to_human_after_5min(self):
        """AI_AUDIT card awaiting >5min should be re-routed to HUMAN (desktop)."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card = _make_shot_card(
            shot_id="shot-ai",
            routing_decision="AI_AUDIT",
            minutes_ago=10,  # 10 minutes old
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_router = AsyncMock()
        mock_router.enqueue = AsyncMock()

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_shot_card_timeouts({})

            assert "shot-ai" in result
            # Verify the card was escalated (routing_decision updated to HUMAN)
            assert card.routing_decision == "HUMAN"
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_creates_audit_entry_on_escalate(self):
        """Escalation should create AuditEntry with action='timeout_escalated'."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card = _make_shot_card(
            shot_id="shot-esc",
            routing_decision="AI_AUDIT",
            minutes_ago=10,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_router = AsyncMock()
        mock_router.enqueue = AsyncMock()

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ) as mock_audit:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await check_shot_card_timeouts({})

            mock_audit.assert_called()
            # Verify action is timeout_escalated
            call_kwargs = mock_audit.call_args
            args = call_kwargs[0] if call_kwargs[0] else []
            kwargs = call_kwargs[1] if call_kwargs[1] else {}
            # Check that action field indicates escalation
            assert "timeout_escalated" in str(args) or "timeout_escalated" in str(kwargs)


class TestWithinThreshold:
    """Test that cards within timeout threshold are not affected."""

    @pytest.mark.asyncio
    async def test_human_card_within_threshold_not_affected(self):
        """HUMAN card that hasn't exceeded 24h should not be touched."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card = _make_shot_card(
            shot_id="shot-fresh",
            routing_decision="HUMAN",
            minutes_ago=30,  # Only 30 min old
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_router = AsyncMock()

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_shot_card_timeouts({})

            assert result == []
            mock_router.reject_single.assert_not_called()
            mock_router.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_audit_card_within_threshold_not_affected(self):
        """AI_AUDIT card that hasn't exceeded 5min should not be touched."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card = _make_shot_card(
            shot_id="shot-fresh-ai",
            routing_decision="AI_AUDIT",
            minutes_ago=2,  # Only 2 min old
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_router = AsyncMock()

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_shot_card_timeouts({})

            assert result == []
            mock_router.reject_single.assert_not_called()


class TestCronReturn:
    """Test cron function returns affected shot_ids."""

    @pytest.mark.asyncio
    async def test_returns_list_of_affected_shot_ids(self):
        """Cron function should return list of shot_ids that were acted on."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        card1 = _make_shot_card(
            shot_id="shot-1", routing_decision="HUMAN", minutes_ago=25 * 60
        )
        card2 = _make_shot_card(
            shot_id="shot-2", routing_decision="AI_AUDIT", minutes_ago=10
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [card1, card2]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_router = AsyncMock()
        mock_router.reject_single = AsyncMock(return_value=True)
        mock_router.enqueue = AsyncMock()

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
            return_value=mock_router,
        ), patch(
            "app.workers.shot_card_timeouts.create_audit_entry",
            new_callable=AsyncMock,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_shot_card_timeouts({})

            assert len(result) == 2
            assert "shot-1" in result
            assert "shot-2" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_timeouts(self):
        """Cron function should return empty list when no cards timed out."""
        from app.workers.shot_card_timeouts import check_shot_card_timeouts

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.workers.shot_card_timeouts.async_session_factory"
        ) as mock_factory, patch(
            "app.workers.shot_card_timeouts.ApprovalRouter",
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_shot_card_timeouts({})

            assert result == []
