"""Tests for the V2 ShotCard-aware policy engine with policy stacking.

Tests ShotCard-to-eval-dict conversion, narrative context field evaluation,
policy stacking (global -> project -> temporary with last-layer-wins),
PolicyResult tracking, and graceful handling of missing fields.
"""

from unittest.mock import MagicMock

import pytest

from app.models.shot_card import RoutingDecision


# ---------------------------------------------------------------------------
# Helpers: build mock ShotCard-like objects
# ---------------------------------------------------------------------------


def make_shot_card(
    project_id="proj-001",
    shot_id="shot-001",
    scene="scene_01",
    shot_number=1,
    emotion_curve="neutral",
    continuity_tags=None,
    audit_status="awaiting_audit",
    routing_decision=None,
    visual_bundle=None,
    audio_bundle=None,
):
    """Build a MagicMock mimicking a ShotCard model instance."""
    card = MagicMock()
    card.project_id = project_id
    card.shot_id = shot_id
    card.audit_status = audit_status
    card.routing_decision = routing_decision
    card.narrative_context = {
        "scene": scene,
        "shot_number": shot_number,
        "emotion_curve": emotion_curve,
        "continuity_tags": continuity_tags or [],
    }
    card.visual_bundle = visual_bundle
    card.audio_bundle = audio_bundle
    return card


def make_shot_card_dict(
    project_id="proj-001",
    shot_id="shot-001",
    scene="scene_01",
    shot_number=1,
    emotion_curve="neutral",
    continuity_tags=None,
    audit_status="awaiting_audit",
    routing_decision=None,
    visual_bundle=None,
    audio_bundle=None,
):
    """Build a plain dict mimicking a ShotCard."""
    return {
        "project_id": project_id,
        "shot_id": shot_id,
        "audit_status": audit_status,
        "routing_decision": routing_decision,
        "narrative_context": {
            "scene": scene,
            "shot_number": shot_number,
            "emotion_curve": emotion_curve,
            "continuity_tags": continuity_tags or [],
        },
        "visual_bundle": visual_bundle,
        "audio_bundle": audio_bundle,
    }


# ---------------------------------------------------------------------------
# Sample policies for stacking tests
# ---------------------------------------------------------------------------

GLOBAL_POLICY_YAML = """\
name: global_routing
version: "1.0"
rules:
  - name: auto_neutral
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.emotion_curve
          operator: equals
          value: neutral
    disposition: AUTO
"""

PROJECT_POLICY_YAML = """\
name: project_high_emotion
version: "1.0"
rules:
  - name: human_high_emotion
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.emotion_curve
          operator: equals
          value: intense
    disposition: HUMAN
"""

TEMPORARY_POLICY_YAML = """\
name: temporary_block_scene
version: "1.0"
rules:
  - name: block_specific_scene
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.scene
          operator: equals
          value: scene_42
    disposition: BLOCK
"""

# Policy that matches emotion_curve via contains on continuity_tags
TAG_POLICY_YAML = """\
name: tag_routing
version: "1.0"
rules:
  - name: horror_needs_human
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.continuity_tags
          operator: contains
          value: horror
    disposition: HUMAN
"""


# ---------------------------------------------------------------------------
# Test: _shot_card_to_eval_dict conversion
# ---------------------------------------------------------------------------


class TestShotCardToEvalDict:
    """Test ShotCard model/dict to flat evaluation dict conversion."""

    def test_converts_basic_fields(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        card = make_shot_card(project_id="p1", shot_id="s1", audit_status="awaiting_audit")
        result = engine._shot_card_to_eval_dict(card)

        assert result["project_id"] == "p1"
        assert result["shot_id"] == "s1"
        assert result["audit_status"] == "awaiting_audit"

    def test_converts_narrative_context(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        card = make_shot_card(
            scene="scene_05",
            shot_number=3,
            emotion_curve="tension",
            continuity_tags=["dark", "horror"],
        )
        result = engine._shot_card_to_eval_dict(card)

        assert result["narrative_context"]["scene"] == "scene_05"
        assert result["narrative_context"]["shot_number"] == 3
        assert result["narrative_context"]["emotion_curve"] == "tension"
        assert result["narrative_context"]["continuity_tags"] == ["dark", "horror"]

    def test_converts_visual_bundle(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        card = make_shot_card(
            visual_bundle={"keyframes": {"first": {"url": "http://example.com/img.jpg"}}}
        )
        result = engine._shot_card_to_eval_dict(card)

        assert result["visual_bundle"]["keyframes"]["first"]["url"] == "http://example.com/img.jpg"

    def test_handles_none_visual_bundle(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        card = make_shot_card(visual_bundle=None)
        result = engine._shot_card_to_eval_dict(card)

        assert "visual_bundle" not in result or result.get("visual_bundle") is None

    def test_handles_dict_input(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        data = make_shot_card_dict(project_id="p2", shot_id="s2")
        result = engine._shot_card_to_eval_dict(data)

        assert result["project_id"] == "p2"
        assert result["narrative_context"]["scene"] == "scene_01"

    def test_handles_empty_narrative_context(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        card = make_shot_card()
        card.narrative_context = {}
        result = engine._shot_card_to_eval_dict(card)

        # Should not crash; narrative_context may be empty dict
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test: evaluate_shot_card
# ---------------------------------------------------------------------------


class TestEvaluateShotCard:
    """Test evaluating a ShotCard against loaded policies."""

    def test_neutral_emotion_auto(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = make_shot_card(emotion_curve="neutral")
        result = engine.evaluate_shot_card(card)

        assert result.disposition == RoutingDecision.AUTO

    def test_intense_emotion_no_match_defaults_human(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = make_shot_card(emotion_curve="intense")
        result = engine.evaluate_shot_card(card)

        # No rule matches "intense" in global policy -> default HUMAN
        assert result.disposition == RoutingDecision.HUMAN

    def test_returns_policy_result(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = make_shot_card(emotion_curve="neutral")
        result = engine.evaluate_shot_card(card)

        assert hasattr(result, "disposition")
        assert hasattr(result, "matched_rule")
        assert hasattr(result, "policy_commit_sha")
        assert hasattr(result, "stack_layers_evaluated")

    def test_evaluates_with_dict(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        data = make_shot_card_dict(emotion_curve="neutral")
        result = engine.evaluate_shot_card(data)

        assert result.disposition == RoutingDecision.AUTO


# ---------------------------------------------------------------------------
# Test: Policy Stacking
# ---------------------------------------------------------------------------


class TestPolicyStacking:
    """Test policy stacking: global -> project -> temporary, last match wins."""

    def _make_stacked_policies(self):
        """Return policies_by_layer dict."""
        import yaml

        return {
            "global": [yaml.safe_load(GLOBAL_POLICY_YAML)],
            "project": [yaml.safe_load(PROJECT_POLICY_YAML)],
            "temporary": [yaml.safe_load(TEMPORARY_POLICY_YAML)],
        }

    def test_global_only_returns_global_result(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        import yaml

        policies = {"global": [yaml.safe_load(GLOBAL_POLICY_YAML)]}

        card = make_shot_card(emotion_curve="neutral")
        result = engine.evaluate_with_stack(card, policies)

        assert result.disposition == RoutingDecision.AUTO

    def test_global_says_auto_project_says_human_human_wins(self):
        """When both global and project match, project layer overrides."""
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        policies = self._make_stacked_policies()

        # "intense" matches project's human_high_emotion rule
        # global auto_neutral does NOT match "intense"
        card = make_shot_card(emotion_curve="intense")
        result = engine.evaluate_with_stack(card, policies)

        assert result.disposition == RoutingDecision.HUMAN

    def test_temporary_overrides_all(self):
        """Temporary layer overrides both global and project."""
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        policies = self._make_stacked_policies()

        # scene_42 matches temporary's block rule; emotion_curve=neutral matches global's auto
        card = make_shot_card(emotion_curve="neutral", scene="scene_42")
        result = engine.evaluate_with_stack(card, policies)

        # Temporary BLOCK overrides global AUTO
        assert result.disposition == RoutingDecision.BLOCK

    def test_no_match_defaults_to_human(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        policies = self._make_stacked_policies()

        card = make_shot_card(emotion_curve="melancholy", scene="scene_99")
        result = engine.evaluate_with_stack(card, policies)

        assert result.disposition == RoutingDecision.HUMAN

    def test_stack_layers_evaluated_tracked(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        policies = self._make_stacked_policies()

        card = make_shot_card(emotion_curve="neutral")
        result = engine.evaluate_with_stack(card, policies)

        assert "global" in result.stack_layers_evaluated

    def test_matched_rule_name_tracked(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        import yaml

        policies = {"global": [yaml.safe_load(GLOBAL_POLICY_YAML)]}

        card = make_shot_card(emotion_curve="neutral")
        result = engine.evaluate_with_stack(card, policies)

        assert result.matched_rule == "auto_neutral"

    def test_global_auto_project_human_same_card_project_wins(self):
        """When a card matches both global AUTO and project HUMAN,
        project's match overrides because it's evaluated later."""
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()

        # Create a project policy that also matches neutral
        project_override_yaml = """\
name: project_override
version: "1.0"
rules:
  - name: human_all_neutral
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.emotion_curve
          operator: equals
          value: neutral
    disposition: HUMAN
"""
        import yaml

        policies = {
            "global": [yaml.safe_load(GLOBAL_POLICY_YAML)],
            "project": [yaml.safe_load(project_override_yaml)],
        }

        card = make_shot_card(emotion_curve="neutral")
        result = engine.evaluate_with_stack(card, policies)

        # Project layer evaluated after global, its HUMAN match wins
        assert result.disposition == RoutingDecision.HUMAN
        assert result.matched_rule == "human_all_neutral"


# ---------------------------------------------------------------------------
# Test: Narrative context field access
# ---------------------------------------------------------------------------


class TestNarrativeContextEvaluation:
    """Test that narrative context fields are accessible in policy rules."""

    def test_continuity_tags_contains(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("tags", TAG_POLICY_YAML)

        card = make_shot_card(continuity_tags=["action", "horror", "night"])
        result = engine.evaluate_shot_card(card)

        assert result.disposition == RoutingDecision.HUMAN

    def test_continuity_tags_not_contains(self):
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("tags", TAG_POLICY_YAML)

        card = make_shot_card(continuity_tags=["comedy", "light"])
        result = engine.evaluate_shot_card(card)

        # No match -> default HUMAN (but not because of the horror rule)
        assert result.disposition == RoutingDecision.HUMAN
        assert result.matched_rule is None

    def test_missing_narrative_context_field_fails_gracefully(self):
        """If narrative_context is missing a field, conditions fail without crash."""
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = make_shot_card()
        card.narrative_context = {}  # Empty -- no emotion_curve field

        result = engine.evaluate_shot_card(card)

        # Should not crash; no match -> default HUMAN
        assert result.disposition == RoutingDecision.HUMAN

    def test_none_narrative_context_fails_gracefully(self):
        """If narrative_context is None, conditions fail without crash."""
        from app.core.policy_v2 import ShotCardPolicyEngine

        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = make_shot_card()
        card.narrative_context = None

        result = engine.evaluate_shot_card(card)

        assert result.disposition == RoutingDecision.HUMAN


# ---------------------------------------------------------------------------
# Test: PolicyResult
# ---------------------------------------------------------------------------


class TestPolicyResult:
    """Test the PolicyResult dataclass."""

    def test_policy_result_fields(self):
        from app.core.policy_v2 import PolicyResult

        result = PolicyResult(
            disposition=RoutingDecision.AUTO,
            policy_commit_sha="abc123",
            matched_rule="auto_rule",
            stack_layers_evaluated=["global"],
        )

        assert result.disposition == RoutingDecision.AUTO
        assert result.policy_commit_sha == "abc123"
        assert result.matched_rule == "auto_rule"
        assert result.stack_layers_evaluated == ["global"]

    def test_policy_result_defaults(self):
        from app.core.policy_v2 import PolicyResult

        result = PolicyResult(
            disposition=RoutingDecision.HUMAN,
            policy_commit_sha=None,
            matched_rule=None,
            stack_layers_evaluated=[],
        )

        assert result.policy_commit_sha is None
        assert result.matched_rule is None
        assert result.stack_layers_evaluated == []
