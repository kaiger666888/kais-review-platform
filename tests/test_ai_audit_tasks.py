"""Tests for AI audit arq tasks: record_shadow_score and write_feedback."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.ai_audit_tasks import record_shadow_score, write_feedback


# ---------------------------------------------------------------------------
# record_shadow_score
# ---------------------------------------------------------------------------


class TestRecordShadowScore:
    @pytest.mark.asyncio
    async def test_returns_recorded_on_success(self):
        """record_shadow_score returns status recorded when ShotCard exists."""
        mock_shot_card = MagicMock()
        mock_shot_card.shot_id = "shot-001"
        mock_shot_card.id = 42

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_shot_card)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_score_vector = MagicMock()
        mock_score_vector.model_dump = MagicMock(return_value={
            "aesthetics": None, "consistency": None, "compliance": None,
            "technical_quality": None, "audio_match": None,
            "plugin_name": "null_scorer", "plugin_version": "0.1.0",
        })

        with patch("app.workers.ai_audit_tasks.async_session_factory") as mock_factory, \
             patch("app.workers.ai_audit_tasks.get_scoring_bus") as mock_get_bus:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_bus = AsyncMock()
            mock_bus.score = AsyncMock(return_value=[mock_score_vector])
            mock_get_bus.return_value = mock_bus

            result = await record_shadow_score(
                ctx={},
                shot_card_id=42,
                human_decision="approved",
            )

        assert result["status"] == "recorded"
        assert result["shot_card_id"] == 42

    @pytest.mark.asyncio
    async def test_returns_error_when_shot_card_not_found(self):
        """record_shadow_score returns error when ShotCard missing."""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        with patch("app.workers.ai_audit_tasks.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await record_shadow_score(
                ctx={},
                shot_card_id=999,
                human_decision="approved",
            )

        assert result["status"] == "error"
        assert result["reason"] == "shot_card_not_found"


# ---------------------------------------------------------------------------
# write_feedback
# ---------------------------------------------------------------------------


class TestWriteFeedback:
    @pytest.mark.asyncio
    async def test_returns_logged_status(self):
        """write_feedback returns status logged (Phase 0 stub)."""
        mock_shot_card = MagicMock()
        mock_shot_card.shot_id = "shot-001"
        mock_shot_card.project_id = "proj-001"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_shot_card)

        with patch("app.workers.ai_audit_tasks.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await write_feedback(
                ctx={},
                shot_card_id=42,
                human_decision="approved",
            )

        assert result["status"] == "logged"

    @pytest.mark.asyncio
    async def test_logs_structured_feedback(self):
        """write_feedback logs structured data via structlog."""
        mock_shot_card = MagicMock()
        mock_shot_card.shot_id = "shot-001"
        mock_shot_card.project_id = "proj-001"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_shot_card)

        with patch("app.workers.ai_audit_tasks.async_session_factory") as mock_factory, \
             patch("app.workers.ai_audit_tasks.logger") as mock_logger:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await write_feedback(
                ctx={},
                shot_card_id=42,
                human_decision="rejected",
            )

            # Verify logger.info was called with feedback data
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["shot_id"] == "shot-001"
            assert call_kwargs["project_id"] == "proj-001"
            assert call_kwargs["human_decision"] == "rejected"


# ---------------------------------------------------------------------------
# WorkerSettings registration
# ---------------------------------------------------------------------------


class TestWorkerSettingsRegistration:
    def test_record_shadow_score_in_functions(self):
        """record_shadow_score is registered in WorkerSettings.functions."""
        from app.workers.tasks import WorkerSettings

        assert record_shadow_score in WorkerSettings.functions

    def test_write_feedback_in_functions(self):
        """write_feedback is registered in WorkerSettings.functions."""
        from app.workers.tasks import WorkerSettings

        assert write_feedback in WorkerSettings.functions
