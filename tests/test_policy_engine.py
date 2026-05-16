"""Unit tests for the YAML policy engine.

Tests policy loading, validation, condition evaluation (AND/OR),
risk-threshold routing, default disposition, and error handling.
"""

import pytest

from app.core.policy import (
    PolicyEngine,
    PolicyValidationError,
    get_policy_engine,
)
from app.models.shot_card import RoutingDecision as Disposition


# --- Sample YAML policies for testing ---

VALID_POLICY_YAML = """\
name: test_policy
version: "1.0"
rules:
  - name: auto_approve_low_risk
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: risk_score
          operator: less_than
          value: 0.3
        - field: source_system
          operator: equals
          value: kais-movie-agent
    disposition: AUTO

  - name: human_review_high_risk
    priority: 2
    conditions:
      operator: OR
      checks:
        - field: risk_score
          operator: greater_than
          value: 0.7
        - field: priority
          operator: equals
          value: critical
    disposition: HUMAN

  - name: block_flagged_content
    priority: 3
    conditions:
      operator: AND
      checks:
        - field: metadata.flagged
          operator: equals
          value: true
    disposition: BLOCK
"""

INVALID_YAML_SYNTAX = """\
name: test
version: "1.0"
rules:
  - name: broken
    conditions:
      operator: AND
      checks: [invalid yaml
"""

MISSING_REQUIRED_FIELD_YAML = """\
name: test_policy
version: "1.0"
rules:
  - name: missing_disposition
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: risk_score
          operator: less_than
          value: 0.3
"""

INVALID_DISPOSITION_YAML = """\
name: test_policy
version: "1.0"
rules:
  - name: bad_disposition
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: risk_score
          operator: less_than
          value: 0.3
    disposition: INVALID_ROUTING
"""

MISSING_NAME_YAML = """\
version: "1.0"
rules:
  - name: some_rule
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: risk_score
          operator: less_than
          value: 0.3
    disposition: AUTO
"""

MISSING_RULES_YAML = """\
name: test_policy
version: "1.0"
"""

MISSING_CONDITIONS_OPERATOR_YAML = """\
name: test_policy
version: "1.0"
rules:
  - name: test_rule
    priority: 1
    conditions:
      checks:
        - field: risk_score
          operator: less_than
          value: 0.3
    disposition: AUTO
"""

OR_OPERATOR_POLICY_YAML = """\
name: or_test
version: "1.0"
rules:
  - name: or_rule
    priority: 1
    conditions:
      operator: OR
      checks:
        - field: risk_score
          operator: greater_than
          value: 0.7
        - field: source_system
          operator: equals
          value: kais-gold-team
    disposition: HUMAN
"""

AI_AUDIT_POLICY_YAML = """\
name: ai_audit_policy
version: "1.0"
rules:
  - name: ai_audit_medium_risk
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: risk_score
          operator: greater_than_or_equal
          value: 0.3
        - field: risk_score
          operator: less_than
          value: 0.7
    disposition: AI_AUDIT
"""


class TestPolicyLoading:
    """Test policy loading and validation."""

    def test_load_valid_policy(self):
        engine = PolicyEngine()
        data = engine.load_policy("test", VALID_POLICY_YAML)
        assert data["name"] == "test_policy"
        assert len(data["rules"]) == 3

    def test_load_from_file(self, tmp_path):
        engine = PolicyEngine()
        policy_file = tmp_path / "test.yaml"
        policy_file.write_text(VALID_POLICY_YAML)
        data = engine.load_from_file(str(policy_file))
        assert data["name"] == "test_policy"

    def test_load_from_directory(self, tmp_path):
        engine = PolicyEngine()
        (tmp_path / "policy_a.yaml").write_text(VALID_POLICY_YAML)
        (tmp_path / "policy_b.yaml").write_text(OR_OPERATOR_POLICY_YAML)
        loaded = engine.load_from_directory(str(tmp_path))
        assert len(loaded) == 2

    def test_validate_policy_returns_dict(self):
        engine = PolicyEngine()
        data = engine.validate_policy(VALID_POLICY_YAML)
        assert isinstance(data, dict)
        assert data["name"] == "test_policy"


class TestPolicyValidation:
    """Test policy validation errors."""

    def test_invalid_yaml_syntax(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="Invalid YAML syntax"):
            engine.validate_policy(INVALID_YAML_SYNTAX)

    def test_missing_required_field_disposition(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="schema validation failed"):
            engine.validate_policy(MISSING_REQUIRED_FIELD_YAML)

    def test_invalid_disposition_value(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="schema validation failed"):
            engine.validate_policy(INVALID_DISPOSITION_YAML)

    def test_missing_name(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="schema validation failed"):
            engine.validate_policy(MISSING_NAME_YAML)

    def test_missing_rules(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="schema validation failed"):
            engine.validate_policy(MISSING_RULES_YAML)

    def test_missing_conditions_operator(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="schema validation failed"):
            engine.validate_policy(MISSING_CONDITIONS_OPERATOR_YAML)

    def test_non_dict_yaml_rejected(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError, match="must be a mapping"):
            engine.validate_policy("- just\n- a\n- list")

    def test_empty_string_rejected(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyValidationError):
            engine.validate_policy("")


class TestPolicyEvaluation:
    """Test policy rule evaluation against review data."""

    def _engine_with_default_policy(self):
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        return engine

    def test_low_risk_from_movie_agent_auto(self):
        engine = self._engine_with_default_policy()
        result = engine.evaluate({
            "risk_score": 0.1,
            "source_system": "kais-movie-agent",
        })
        assert result == Disposition.AUTO

    def test_high_risk_human(self):
        engine = self._engine_with_default_policy()
        result = engine.evaluate({
            "risk_score": 0.8,
            "source_system": "kais-movie-agent",
        })
        assert result == Disposition.HUMAN

    def test_critical_priority_human(self):
        """Critical priority triggers HUMAN for non-auto source systems."""
        engine = self._engine_with_default_policy()
        result = engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-gold-team",
            "priority": "critical",
        })
        assert result == Disposition.HUMAN

    def test_flagged_content_blocked(self):
        """Flagged content from non-movie-agent source is blocked."""
        engine = self._engine_with_default_policy()
        result = engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-gold-team",
            "metadata": {"flagged": True},
        })
        assert result == Disposition.BLOCK

    def test_no_matching_rule_defaults_to_human(self):
        """When no rules match, default disposition is HUMAN."""
        engine = self._engine_with_default_policy()
        result = engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-movie-agent",
        })
        assert result == Disposition.HUMAN

    def test_empty_engine_defaults_to_human(self):
        """Engine with no policies returns HUMAN."""
        engine = PolicyEngine()
        result = engine.evaluate({"risk_score": 0.1})
        assert result == Disposition.HUMAN


class TestANDOperator:
    """Test AND operator: ALL checks must be true."""

    def test_all_conditions_true(self):
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        # risk_score < 0.3 AND source_system == kais-movie-agent
        result = engine.evaluate({
            "risk_score": 0.1,
            "source_system": "kais-movie-agent",
        })
        assert result == Disposition.AUTO

    def test_one_condition_false(self):
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        # risk_score < 0.3 but source_system != kais-movie-agent
        result = engine.evaluate({
            "risk_score": 0.1,
            "source_system": "kais-gold-team",
        })
        # Should not match AUTO rule; falls to next rules
        assert result != Disposition.AUTO


class TestOROperator:
    """Test OR operator: ANY check being true is sufficient."""

    def test_first_condition_true(self):
        engine = PolicyEngine()
        engine.load_policy("test", OR_OPERATOR_POLICY_YAML)
        result = engine.evaluate({
            "risk_score": 0.9,
            "source_system": "kais-movie-agent",
        })
        assert result == Disposition.HUMAN

    def test_second_condition_true(self):
        engine = PolicyEngine()
        engine.load_policy("test", OR_OPERATOR_POLICY_YAML)
        result = engine.evaluate({
            "risk_score": 0.1,
            "source_system": "kais-gold-team",
        })
        assert result == Disposition.HUMAN

    def test_no_conditions_true(self):
        engine = PolicyEngine()
        engine.load_policy("test", OR_OPERATOR_POLICY_YAML)
        result = engine.evaluate({
            "risk_score": 0.3,
            "source_system": "kais-movie-agent",
        })
        # No match, defaults to HUMAN
        assert result == Disposition.HUMAN


class TestConditionOperators:
    """Test individual condition operators."""

    def _single_rule_engine(self, field, op, value, disposition="AUTO"):
        yaml_str = f"""\
name: test
version: "1.0"
rules:
  - name: rule
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: {field}
          operator: {op}
          value: {value}
    disposition: {disposition}
"""
        engine = PolicyEngine()
        engine.load_policy("test", yaml_str)
        return engine

    def test_equals(self):
        engine = self._single_rule_engine("source_system", "equals", '"kais-movie-agent"')
        assert engine.evaluate({"source_system": "kais-movie-agent"}) == Disposition.AUTO
        assert engine.evaluate({"source_system": "other"}) == Disposition.HUMAN

    def test_not_equals(self):
        engine = self._single_rule_engine("source_system", "not_equals", '"kais-movie-agent"')
        assert engine.evaluate({"source_system": "other"}) == Disposition.AUTO
        assert engine.evaluate({"source_system": "kais-movie-agent"}) == Disposition.HUMAN

    def test_greater_than(self):
        engine = self._single_rule_engine("risk_score", "greater_than", "0.5")
        assert engine.evaluate({"risk_score": 0.7}) == Disposition.AUTO
        assert engine.evaluate({"risk_score": 0.3}) == Disposition.HUMAN

    def test_less_than(self):
        engine = self._single_rule_engine("risk_score", "less_than", "0.3")
        assert engine.evaluate({"risk_score": 0.1}) == Disposition.AUTO
        assert engine.evaluate({"risk_score": 0.5}) == Disposition.HUMAN

    def test_greater_than_or_equal(self):
        engine = self._single_rule_engine("risk_score", "greater_than_or_equal", "0.5")
        assert engine.evaluate({"risk_score": 0.5}) == Disposition.AUTO
        assert engine.evaluate({"risk_score": 0.4}) == Disposition.HUMAN

    def test_less_than_or_equal(self):
        engine = self._single_rule_engine("risk_score", "less_than_or_equal", "0.5")
        assert engine.evaluate({"risk_score": 0.5}) == Disposition.AUTO
        assert engine.evaluate({"risk_score": 0.6}) == Disposition.HUMAN

    def test_contains_string(self):
        engine = self._single_rule_engine("content_ref", "contains", '"video"')
        assert engine.evaluate({"content_ref": "s3://bucket/video-001.mp4"}) == Disposition.AUTO
        assert engine.evaluate({"content_ref": "s3://bucket/image-001.jpg"}) == Disposition.HUMAN

    def test_in_list(self):
        engine = self._single_rule_engine("source_system", "in", '["kais-movie-agent", "kais-gold-team"]')
        assert engine.evaluate({"source_system": "kais-movie-agent"}) == Disposition.AUTO
        assert engine.evaluate({"source_system": "unknown"}) == Disposition.HUMAN


class TestDottedFieldAccess:
    """Test dotted field access for nested data."""

    def test_nested_metadata_field(self):
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        result = engine.evaluate({
            "risk_score": 0.1,
            "source_system": "kais-movie-agent",
            "metadata": {"flagged": True},
        })
        # The block_flagged_content rule should match before auto_approve
        # because priority ordering: auto=1, human=2, block=3
        # Wait -- auto has priority 1 and matches first, so flagged=True won't block
        # This is actually a test that priority order matters
        assert result == Disposition.AUTO

    def test_flagged_blocks_when_no_auto_match(self):
        """Flagged content from non-movie-agent source should be blocked."""
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        result = engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-gold-team",
            "metadata": {"flagged": True},
        })
        assert result == Disposition.BLOCK

    def test_missing_nested_field_fails_gracefully(self):
        """Missing nested field causes condition to fail (not crash)."""
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        # metadata exists but 'flagged' key is missing
        result = engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-gold-team",
            "metadata": {"other_key": "value"},
        })
        # No rule matches -> HUMAN default
        assert result == Disposition.HUMAN


class TestPolicyManagement:
    """Test policy engine management operations."""

    def test_list_policies(self):
        engine = PolicyEngine()
        engine.load_policy("beta", VALID_POLICY_YAML)
        engine.load_policy("alpha", OR_OPERATOR_POLICY_YAML)
        assert engine.list_policies() == ["alpha", "beta"]  # sorted

    def test_get_policy(self):
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        policy = engine.get_policy("test")
        assert policy is not None
        assert policy["name"] == "test_policy"

    def test_get_nonexistent_policy_returns_none(self):
        engine = PolicyEngine()
        assert engine.get_policy("nonexistent") is None

    def test_remove_policy(self):
        engine = PolicyEngine()
        engine.load_policy("test", VALID_POLICY_YAML)
        assert engine.remove_policy("test") is True
        assert engine.get_policy("test") is None

    def test_remove_nonexistent_policy(self):
        engine = PolicyEngine()
        assert engine.remove_policy("nonexistent") is False

    def test_get_policy_engine_singleton(self):
        """Module-level get_policy_engine returns singleton."""
        e1 = get_policy_engine()
        e2 = get_policy_engine()
        assert e1 is e2


class TestDefaultYamlPolicy:
    """Test the actual default.yaml policy file shipped with the project."""

    def test_load_default_yaml(self):
        import os
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app",
            "policies",
            "default.yaml",
        )
        engine = PolicyEngine()
        data = engine.load_from_file(default_path)
        assert data["name"] == "default_routing"
        assert len(data["rules"]) == 3

    def test_evaluate_with_default_yaml(self):
        import os
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app",
            "policies",
            "default.yaml",
        )
        engine = PolicyEngine()
        engine.load_from_file(default_path)

        # Low risk movie agent -> AUTO
        assert engine.evaluate({
            "risk_score": 0.1,
            "source_system": "kais-movie-agent",
        }) == Disposition.AUTO

        # High risk -> HUMAN
        assert engine.evaluate({
            "risk_score": 0.8,
            "source_system": "kais-movie-agent",
        }) == Disposition.HUMAN

        # Critical priority -> HUMAN (non-auto source so AUTO rule doesn't match first)
        assert engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-gold-team",
            "priority": "critical",
        }) == Disposition.HUMAN

        # Flagged -> BLOCK (non-auto source)
        assert engine.evaluate({
            "risk_score": 0.5,
            "source_system": "kais-gold-team",
            "metadata": {"flagged": True},
        }) == Disposition.BLOCK
