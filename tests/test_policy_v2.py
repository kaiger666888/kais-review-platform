"""Tests for ShotCardPolicyEngine: Shot Card evaluation, policy stacking,
narrative context awareness, and PolicyResult tracking."""

import pytest
from unittest.mock import MagicMock

from app.core.policy_v2 import ShotCardPolicyEngine, PolicyResult
from app.models.schemas import Disposition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_shot_card(
    shot_id="shot-001",
    project_id="proj-001",
    audit_status="awaiting_audit",
    narrative_context=None,
    visual_bundle=None,
    routing_decision=None,
):
    """Create a MagicMock ShotCard-like object with configurable attributes."""
    card = MagicMock()
    card.shot_id = shot_id
    card.project_id = project_id
    card.audit_status = audit_status
    card.narrative_context = narrative_context or {
        "scene": "scene-01",
        "shot_number": 1,
        "emotion_curve": "neutral",
        "continuity_tags": ["daytime", "interior"],
    }
    card.visual_bundle = visual_bundle
    card.routing_decision = routing_decision
    return card


# Sample YAML policies for stacking tests

GLOBAL_POLICY_YAML = """\
name: global_routing
version: "1.0"
rules:
  - name: auto_low_emotion
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.emotion_curve
          operator: equals
          value: neutral
    disposition: AUTO

  - name: human_high_emotion
    priority: 2
    conditions:
      operator: OR
      checks:
        - field: narrative_context.emotion_curve
          operator: equals
          value: intense
    disposition: HUMAN
"""

PROJECT_POLICY_YAML = """\
name: project_strict
version: "1.0"
rules:
  - name: block_flagged_tags
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.continuity_tags
          operator: contains
          value: flagged
    disposition: BLOCK

  - name: human_night_scene
    priority: 2
    conditions:
      operator: AND
      checks:
        - field: narrative_context.scene
          operator: equals
          value: night-ext
    disposition: HUMAN
"""

TEMPORARY_POLICY_YAML = """\
name: temp_override
version: "1.0"
rules:
  - name: block_all_for_project
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: project_id
          operator: equals
          value: proj-001
    disposition: BLOCK
"""


# ---------------------------------------------------------------------------
# Task 1 Tests: ShotCardPolicyEngine
# ---------------------------------------------------------------------------


class TestShotCardToEvalDict:
    """Test _shot_card_to_eval_dict converts ShotCard to flat eval dict."""

    def test_basic_field_mapping(self):
        """ShotCard fields map to top-level eval dict keys."""
        engine = ShotCardPolicyEngine()
        card = _make_shot_card(
            shot_id="shot-001",
            project_id="proj-001",
            audit_status="awaiting_audit",
        )
        result = engine._shot_card_to_eval_dict(card)

        assert result["shot_id"] == "shot-001"
        assert result["project_id"] == "proj-001"
        assert result["audit_status"] == "awaiting_audit"

    def test_narrative_context_preserved_as_nested_dict(self):
        """narrative_context fields remain accessible via dotted path."""
        engine = ShotCardPolicyEngine()
        card = _make_shot_card(
            narrative_context={
                "scene": "forest",
                "shot_number": 5,
                "emotion_curve": "tense",
                "continuity_tags": ["outdoor", "sunset"],
            }
        )
        result = engine._shot_card_to_eval_dict(card)

        assert result["narrative_context"]["scene"] == "forest"
        assert result["narrative_context"]["shot_number"] == 5
        assert result["narrative_context"]["emotion_curve"] == "tense"
        assert result["narrative_context"]["continuity_tags"] == ["outdoor", "sunset"]

    def test_visual_bundle_keyframes_accessible(self):
        """visual_bundle nested fields are dot-accessible."""
        engine = ShotCardPolicyEngine()
        card = _make_shot_card(
            visual_bundle={
                "keyframes": {"first": "frame_001.png", "last": "frame_050.png"},
                "video_url": "https://example.com/video.mp4",
            }
        )
        result = engine._shot_card_to_eval_dict(card)

        assert result["visual_bundle"]["keyframes"]["first"] == "frame_001.png"

    def test_none_visual_bundle_handled(self):
        """None visual_bundle does not crash conversion."""
        engine = ShotCardPolicyEngine()
        card = _make_shot_card(visual_bundle=None)
        result = engine._shot_card_to_eval_dict(card)

        assert result["visual_bundle"] is None

    def test_dict_input_accepted(self):
        """_shot_card_to_eval_dict also accepts a plain dict."""
        engine = ShotCardPolicyEngine()
        data = {
            "shot_id": "shot-002",
            "project_id": "proj-002",
            "audit_status": "approved",
            "narrative_context": {"scene": "beach", "shot_number": 3},
        }
        result = engine._shot_card_to_eval_dict(data)

        assert result["shot_id"] == "shot-002"
        assert result["narrative_context"]["scene"] == "beach"


class TestEvaluateShotCard:
    """Test evaluate_shot_card() returns correct Disposition."""

    def test_neutral_emotion_auto_approved(self):
        """Neutral emotion curve triggers AUTO disposition."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior"],
            }
        )
        result = engine.evaluate_shot_card(card, policy_name="global")

        assert result.disposition == Disposition.AUTO

    def test_intense_emotion_human_review(self):
        """Intense emotion curve triggers HUMAN disposition."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "battle",
                "shot_number": 1,
                "emotion_curve": "intense",
                "continuity_tags": ["exterior"],
            }
        )
        result = engine.evaluate_shot_card(card, policy_name="global")

        assert result.disposition == Disposition.HUMAN

    def test_no_matching_rule_defaults_to_human(self):
        """When no rule matches, default to HUMAN (safe conservative)."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "forest",
                "shot_number": 1,
                "emotion_curve": "mild",
                "continuity_tags": [],
            }
        )
        result = engine.evaluate_shot_card(card, policy_name="global")

        assert result.disposition == Disposition.HUMAN

    def test_continuity_tags_contains_operator(self):
        """The contains operator works on continuity_tags list."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("project", PROJECT_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior", "flagged"],
            }
        )
        result = engine.evaluate_shot_card(card, policy_name="project")

        assert result.disposition == Disposition.BLOCK

    def test_missing_narrative_context_field_fails_gracefully(self):
        """Missing narrative_context field causes condition to fail, not crash."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "office",
                # Missing emotion_curve and continuity_tags
            }
        )
        # Should not raise -- condition fails gracefully, default HUMAN
        result = engine.evaluate_shot_card(card, policy_name="global")

        assert result.disposition == Disposition.HUMAN

    def test_returns_policy_result(self):
        """evaluate_shot_card returns a PolicyResult with tracking info."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior"],
            }
        )
        result = engine.evaluate_shot_card(card, policy_name="global")

        assert isinstance(result, PolicyResult)
        assert result.disposition == Disposition.AUTO
        assert result.matched_rule == "auto_low_emotion"
        assert isinstance(result.stack_layers_evaluated, list)


class TestPolicyStacking:
    """Test evaluate_with_stack: global -> project -> temporary precedence."""

    def test_global_only_uses_global_result(self):
        """When only global policy exists, uses global result."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior"],
            }
        )
        result = engine.evaluate_with_stack(
            card,
            policies_by_layer={"global": ["global"]},
        )

        assert result.disposition == Disposition.AUTO
        assert "global" in result.stack_layers_evaluated

    def test_project_overrides_global(self):
        """Project policy overrides global when project rule matches."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)
        engine.load_policy("project", PROJECT_POLICY_YAML)

        # Global says AUTO (neutral emotion), but project says BLOCK (flagged tag)
        card = _make_shot_card(
            project_id="proj-001",
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior", "flagged"],
            }
        )
        result = engine.evaluate_with_stack(
            card,
            policies_by_layer={"global": ["global"], "project": ["project"]},
        )

        assert result.disposition == Disposition.BLOCK
        assert "global" in result.stack_layers_evaluated
        assert "project" in result.stack_layers_evaluated

    def test_temporary_overrides_all(self):
        """Temporary policy overrides both global and project."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)
        engine.load_policy("project", PROJECT_POLICY_YAML)
        engine.load_policy("temporary", TEMPORARY_POLICY_YAML)

        # Global: AUTO (neutral), Project: no match, Temporary: BLOCK (proj-001)
        card = _make_shot_card(
            project_id="proj-001",
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior"],
            }
        )
        result = engine.evaluate_with_stack(
            card,
            policies_by_layer={
                "global": ["global"],
                "project": ["project"],
                "temporary": ["temporary"],
            },
        )

        assert result.disposition == Disposition.BLOCK
        assert result.matched_rule == "block_all_for_project"
        assert len(result.stack_layers_evaluated) == 3

    def test_stacking_no_match_in_later_layer_keeps_earlier(self):
        """If a later layer has no match, earlier result stands."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)
        engine.load_policy("project", PROJECT_POLICY_YAML)

        # Global: AUTO (neutral), Project: no match (not flagged, not night-ext)
        card = _make_shot_card(
            project_id="proj-002",
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior"],
            }
        )
        result = engine.evaluate_with_stack(
            card,
            policies_by_layer={"global": ["global"], "project": ["project"]},
        )

        # Global's AUTO stands since project had no match
        assert result.disposition == Disposition.AUTO

    def test_empty_stack_defaults_to_human(self):
        """Empty policy stack returns HUMAN default."""
        engine = ShotCardPolicyEngine()

        card = _make_shot_card()
        result = engine.evaluate_with_stack(
            card,
            policies_by_layer={},
        )

        assert result.disposition == Disposition.HUMAN

    def test_policy_result_tracks_commit_sha(self):
        """PolicyResult stores policy_commit_sha when provided."""
        engine = ShotCardPolicyEngine()
        engine.load_policy("global", GLOBAL_POLICY_YAML)

        card = _make_shot_card(
            narrative_context={
                "scene": "office",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "continuity_tags": ["interior"],
            }
        )
        result = engine.evaluate_with_stack(
            card,
            policies_by_layer={"global": ["global"]},
            policy_commit_sha="abc123def456",
        )

        assert result.policy_commit_sha == "abc123def456"


class TestLoadPoliciesFromLayer:
    """Test batch loading policies for a named layer."""

    def test_load_multiple_policies_for_layer(self):
        """load_policies_from_layer loads multiple YAML strings under prefixed names."""
        engine = ShotCardPolicyEngine()

        yaml_a = """\
name: policy_a
version: "1.0"
rules:
  - name: rule_a
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: project_id
          operator: equals
          value: proj-a
    disposition: AUTO
"""
        yaml_b = """\
name: policy_b
version: "1.0"
rules:
  - name: rule_b
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: project_id
          operator: equals
          value: proj-b
    disposition: BLOCK
"""
        names = engine.load_policies_from_layer(
            {"policy_a": yaml_a, "policy_b": yaml_b}, "test_layer"
        )

        assert len(names) == 2
        # Verify loaded policies exist
        assert engine.get_policy("policy_a") is not None
        assert engine.get_policy("policy_b") is not None
