"""Integration tests for policy evaluation in the aggregation pipeline.

Tests that the ShotCardAggregator correctly:
- Evaluates policy when min_audit_set is satisfied
- Writes policy_commit_sha and routing_decision to ShotCard provenance
- Creates AuditEntry with policy evaluation details
- Skips evaluation when min_audit_set is NOT satisfied
- Uses GitProvider to obtain policies
- Evaluates policy only once per ShotCard (not re-evaluated on subsequent events)
- Returns policy_result in the handle_node_completion summary dict
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import Disposition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_shot_card(
    shot_id="shot-001",
    project_id="proj-001",
    audit_status="awaiting_audit",
    routing_decision=None,
    narrative_context=None,
    visual_bundle=None,
    policy_commit_sha=None,
):
    """Create a MagicMock ShotCard-like object."""
    card = MagicMock()
    card.id = 1
    card.shot_id = shot_id
    card.project_id = project_id
    card.audit_status = audit_status
    card.routing_decision = routing_decision
    card.policy_commit_sha = policy_commit_sha
    card.narrative_context = narrative_context or {
        "scene": "office",
        "shot_number": 1,
        "emotion_curve": "neutral",
        "continuity_tags": ["interior"],
    }
    card.visual_bundle = visual_bundle
    card.audio_bundle = None
    card.min_audit_set = ["visual_bundle"]
    return card


# Sample policies returned by GitPolicyProvider
GLOBAL_POLICY_DICT = {
    "name": "global_routing",
    "version": "1.0",
    "rules": [
        {
            "name": "auto_low_emotion",
            "priority": 1,
            "conditions": {
                "operator": "AND",
                "checks": [
                    {
                        "field": "narrative_context.emotion_curve",
                        "operator": "equals",
                        "value": "neutral",
                    }
                ],
            },
            "disposition": "AUTO",
        }
    ],
}

PROJECT_POLICY_DICT = {
    "name": "project_strict",
    "version": "1.0",
    "rules": [
        {
            "name": "block_flagged",
            "priority": 1,
            "conditions": {
                "operator": "AND",
                "checks": [
                    {
                        "field": "narrative_context.continuity_tags",
                        "operator": "contains",
                        "value": "flagged",
                    }
                ],
            },
            "disposition": "BLOCK",
        }
    ],
}


def _make_mock_git_provider(commit_sha="abc123def456"):
    """Create a mock GitPolicyProvider that returns test policies."""
    provider = AsyncMock()
    provider.get_policies = AsyncMock(
        return_value=(
            {
                "global": {"routing.yaml": GLOBAL_POLICY_DICT},
                "projects": {"proj-001": {"strict.yaml": PROJECT_POLICY_DICT}},
            },
            commit_sha,
        )
    )
    provider.get_policies_for_project = AsyncMock(
        return_value={
            "global": [GLOBAL_POLICY_DICT],
            "project": [PROJECT_POLICY_DICT],
        }
    )
    return provider


# ---------------------------------------------------------------------------
# Task 1 Tests
# ---------------------------------------------------------------------------


class TestPolicyEvaluationInAggregator:
    """Test policy evaluation is wired into the aggregation pipeline."""

    @pytest.mark.asyncio
    async def test_policy_evaluated_when_min_audit_satisfied(self):
        """When min_audit_set is satisfied, aggregator evaluates policy and writes routing_decision."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        # Shot card with routing_decision=None (not yet evaluated)
        mock_card = _make_shot_card(routing_decision=None)
        aggregator._ensure_shot_card = AsyncMock(return_value=mock_card)
        aggregator.filler.fill = AsyncMock(return_value=mock_card)
        aggregator.filler.check_min_audit_set = MagicMock(return_value=True)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=False)
        aggregator._emit_events = AsyncMock()

        # Mock provenance writeback and audit entry
        aggregator._evaluate_policy = AsyncMock(
            return_value={
                "result": MagicMock(
                    disposition=Disposition.AUTO,
                    matched_rule="auto_low_emotion",
                    stack_layers_evaluated=["global"],
                    policy_commit_sha="abc123",
                ),
                "commit_sha": "abc123",
            }
        )
        aggregator._write_provenance = AsyncMock(return_value=mock_card)
        aggregator._create_audit_entry = AsyncMock()

        event = {
            "execution_id": "exec-001",
            "shot_id": "shot-001",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png", "hash": "abc"},
        }

        result = await aggregator.handle_node_completion(event)

        # Policy evaluation was called
        aggregator._evaluate_policy.assert_called_once_with(mock_card)
        # Provenance was written
        aggregator._write_provenance.assert_called_once()
        # Audit entry was created
        aggregator._create_audit_entry.assert_called_once()
        # Result includes policy_result
        assert "policy_result" in result
        assert result["policy_result"]["result"].disposition == Disposition.AUTO

    @pytest.mark.asyncio
    async def test_no_policy_evaluation_when_min_audit_not_satisfied(self):
        """When min_audit_set is NOT satisfied, no policy evaluation happens."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        mock_card = _make_shot_card(routing_decision=None)
        aggregator._ensure_shot_card = AsyncMock(return_value=mock_card)
        aggregator.filler.fill = AsyncMock(return_value=mock_card)
        aggregator.filler.check_min_audit_set = MagicMock(return_value=False)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=False)
        aggregator._emit_events = AsyncMock()
        aggregator._evaluate_policy = AsyncMock()
        aggregator._write_provenance = AsyncMock()
        aggregator._create_audit_entry = AsyncMock()

        event = {
            "execution_id": "exec-002",
            "shot_id": "shot-002",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png", "hash": "abc"},
        }

        result = await aggregator.handle_node_completion(event)

        # No policy evaluation
        aggregator._evaluate_policy.assert_not_called()
        aggregator._write_provenance.assert_not_called()
        aggregator._create_audit_entry.assert_not_called()
        # No policy_result in output
        assert result.get("policy_result") is None

    @pytest.mark.asyncio
    async def test_policy_evaluated_only_once_per_shot_card(self):
        """Multiple node completions for same shot_id only evaluate policy once (when first satisfied)."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        # First call: routing_decision=None (first time satisfied)
        mock_card_first = _make_shot_card(routing_decision=None)
        # Second call: routing_decision already set
        mock_card_second = _make_shot_card(routing_decision="AUTO")

        aggregator._ensure_shot_card = AsyncMock(
            side_effect=[mock_card_first, mock_card_second]
        )
        aggregator.filler.fill = AsyncMock(
            side_effect=[mock_card_first, mock_card_second]
        )
        aggregator.filler.check_min_audit_set = MagicMock(return_value=True)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=False)
        aggregator._emit_events = AsyncMock()
        aggregator._evaluate_policy = AsyncMock(
            return_value={
                "result": MagicMock(
                    disposition=Disposition.AUTO,
                    matched_rule="auto_low_emotion",
                    stack_layers_evaluated=["global"],
                    policy_commit_sha="abc123",
                ),
                "commit_sha": "abc123",
            }
        )
        aggregator._write_provenance = AsyncMock(return_value=mock_card_first)
        aggregator._create_audit_entry = AsyncMock()

        event = {
            "execution_id": "exec-003",
            "shot_id": "shot-003",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png", "hash": "abc"},
        }

        # First call: routing_decision=None -> evaluates
        result1 = await aggregator.handle_node_completion(event)
        aggregator._evaluate_policy.assert_called_once()

        # Second call: routing_decision="AUTO" -> skip evaluation
        result2 = await aggregator.handle_node_completion(event)
        # Still only called once
        assert aggregator._evaluate_policy.call_count == 1
        # No policy_result for second call
        assert result2.get("policy_result") is None

    @pytest.mark.asyncio
    async def test_handle_node_completion_returns_policy_result(self):
        """handle_node_completion returns policy_result in the summary dict."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        mock_card = _make_shot_card(routing_decision=None)
        aggregator._ensure_shot_card = AsyncMock(return_value=mock_card)
        aggregator.filler.fill = AsyncMock(return_value=mock_card)
        aggregator.filler.check_min_audit_set = MagicMock(return_value=True)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=False)
        aggregator._emit_events = AsyncMock()

        policy_result = MagicMock(
            disposition=Disposition.HUMAN,
            matched_rule="human_high_emotion",
            stack_layers_evaluated=["global", "project"],
            policy_commit_sha="def456",
        )
        aggregator._evaluate_policy = AsyncMock(
            return_value={
                "result": policy_result,
                "commit_sha": "def456",
            }
        )
        aggregator._write_provenance = AsyncMock(return_value=mock_card)
        aggregator._create_audit_entry = AsyncMock()

        event = {
            "execution_id": "exec-004",
            "shot_id": "shot-004",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png", "hash": "abc"},
        }

        result = await aggregator.handle_node_completion(event)

        assert result["status"] == "ok"
        assert result["policy_result"]["result"].disposition == Disposition.HUMAN
        assert result["policy_result"]["commit_sha"] == "def456"


class TestPolicyEvaluationUsesGitProvider:
    """Test that _evaluate_policy correctly uses GitPolicyProvider."""

    @pytest.mark.asyncio
    async def test_evaluate_policy_calls_git_provider(self):
        """_evaluate_policy calls GitPolicyProvider.get_policies and evaluates."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()
        mock_provider = _make_mock_git_provider("sha789")

        # Patch get_git_policy_provider to return our mock
        with patch(
            "app.services.aggregator.get_git_policy_provider",
            return_value=mock_provider,
        ):
            shot_card = _make_shot_card()
            result = await aggregator._evaluate_policy(shot_card)

            # GitProvider.get_policies was called
            mock_provider.get_policies.assert_called_once()
            # Result has commit_sha from git provider
            assert result["commit_sha"] == "sha789"
            # Result has a PolicyResult
            assert result["result"] is not None
            assert isinstance(result["result"].disposition, Disposition)


class TestWriteProvenance:
    """Test _write_provenance writes routing_decision and policy_commit_sha."""

    @pytest.mark.asyncio
    async def test_write_provenance_updates_shot_card(self):
        """_write_provenance sets routing_decision and policy_commit_sha on ShotCard."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        mock_card = _make_shot_card()
        policy_result = MagicMock(
            disposition=Disposition.AUTO,
            matched_rule="auto_low_emotion",
            stack_layers_evaluated=["global"],
            policy_commit_sha="abc123",
        )
        policy_dict = {"result": policy_result, "commit_sha": "abc123"}

        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_card
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch(
            "app.services.aggregator.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            updated = await aggregator._write_provenance(mock_card, policy_dict)

            # routing_decision was set
            assert mock_card.routing_decision == "AUTO"
            # policy_commit_sha was set
            assert mock_card.policy_commit_sha == "abc123"
            # Session was committed
            mock_session.commit.assert_called_once()


class TestCreateAuditEntry:
    """Test _create_audit_entry creates an AuditEntry with policy details."""

    @pytest.mark.asyncio
    async def test_create_audit_entry_with_policy_details(self):
        """_create_audit_entry creates AuditEntry with action='policy_evaluated'."""
        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        mock_card = _make_shot_card()
        mock_card.id = 42
        policy_result = MagicMock(
            disposition=Disposition.AUTO,
            matched_rule="auto_low_emotion",
            stack_layers_evaluated=["global", "project"],
            policy_commit_sha="abc123",
        )
        policy_dict = {"result": policy_result, "commit_sha": "abc123"}

        # Mock database session
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "app.services.aggregator.async_session_factory"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await aggregator._create_audit_entry(mock_card, policy_dict)

            # AuditEntry was added to session
            mock_session.add.assert_called_once()
            audit_entry = mock_session.add.call_args[0][0]
            assert audit_entry.shot_card_id == 42
            assert audit_entry.action == "policy_evaluated"
            assert audit_entry.actor == "system:policy_engine"
            assert audit_entry.to_state == "AUTO"
            assert audit_entry.payload["matched_rule"] == "auto_low_emotion"
            assert audit_entry.payload["policy_commit_sha"] == "abc123"
            assert audit_entry.payload["stack_layers"] == ["global", "project"]

            mock_session.commit.assert_called_once()
