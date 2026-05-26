"""YAML policy engine with JSON Schema validation and AND/OR condition evaluation.

Loads YAML policy files, validates them against a JSON Schema, and evaluates
review payloads against policy rules to determine routing disposition
(AUTO/HUMAN/AI_AUDIT/BLOCK). When no rules match, the default disposition
is HUMAN (safe conservative default).
"""

from pathlib import Path

import jsonschema
import yaml

from app.models.shot_card import RoutingDecision as Disposition

# ---------------------------------------------------------------------------
# JSON Schema for policy YAML validation
# ---------------------------------------------------------------------------

POLICY_JSON_SCHEMA = {
    "type": "object",
    "required": ["name", "version", "rules"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "pattern": r"^\d+\.\d+$"},
        "rules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "priority", "conditions", "disposition"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "priority": {"type": "integer", "minimum": 1},
                    "conditions": {
                        "type": "object",
                        "required": ["operator", "checks"],
                        "properties": {
                            "operator": {
                                "type": "string",
                                "enum": ["AND", "OR"],
                            },
                            "checks": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": ["field", "operator", "value"],
                                    "properties": {
                                        "field": {"type": "string"},
                                        "operator": {
                                            "type": "string",
                                            "enum": [
                                                "equals",
                                                "not_equals",
                                                "greater_than",
                                                "less_than",
                                                "greater_than_or_equal",
                                                "less_than_or_equal",
                                                "contains",
                                                "in",
                                            ],
                                        },
                                        "value": {},
                                    },
                                },
                            },
                        },
                    },
                    "disposition": {
                        "type": "string",
                        "enum": ["AUTO", "HUMAN", "AI_AUDIT", "BLOCK"],
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PolicyError(Exception):
    """Base exception for policy errors."""


class PolicyValidationError(PolicyError):
    """Raised when a policy fails YAML syntax or JSON Schema validation."""


class PolicyEvaluationError(PolicyError):
    """Raised when policy evaluation encounters an unexpected error."""


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """In-memory policy engine.

    Policies are loaded from YAML files or raw YAML strings, validated
    against the JSON Schema, and stored for evaluation against review data.
    """

    def __init__(self) -> None:
        self._policies: dict[str, dict] = {}  # name -> parsed policy dict

    # -- Loading / Validation ------------------------------------------------

    def validate_policy(self, yaml_content: str) -> dict:
        """Parse and validate YAML policy content.

        Returns the parsed dict on success.
        Raises PolicyValidationError on invalid YAML or schema mismatch.
        """
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as exc:
            raise PolicyValidationError(f"Invalid YAML syntax: {exc}") from exc

        if not isinstance(data, dict):
            raise PolicyValidationError(
                "Policy YAML must be a mapping (object), got "
                f"{type(data).__name__}"
            )

        try:
            jsonschema.validate(instance=data, schema=POLICY_JSON_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise PolicyValidationError(
                f"Policy schema validation failed: {exc.message}"
            ) from exc

        return data

    def load_policy(self, name: str, yaml_content: str) -> dict:
        """Validate and store a policy. Returns parsed dict."""
        data = self.validate_policy(yaml_content)
        self._policies[name] = data
        return data

    def load_from_file(self, filepath: str) -> dict:
        """Load policy from a YAML file path."""
        with open(filepath, "r") as fh:
            content = fh.read()
        data = self.validate_policy(content)
        self._policies[data["name"]] = data
        return data

    def load_from_directory(self, dirpath: str) -> list[str]:
        """Load all .yaml files from a directory. Returns list of loaded names."""
        loaded: list[str] = []
        for filename in sorted(Path(dirpath).glob("*.yaml")):
            data = self.load_from_file(str(filename))
            loaded.append(data["name"])
        return loaded

    # -- Evaluation ----------------------------------------------------------

    def evaluate(
        self, review_data: dict, policy_name: str | None = None
    ) -> Disposition:
        """Evaluate review data against policy rules.

        If *policy_name* is given only that policy is evaluated; otherwise
        all loaded policies are evaluated in alphabetical order by name.
        Rules within each policy are evaluated by ascending priority.
        Returns the Disposition of the first matching rule, or HUMAN when
        no rules match (safe conservative default).
        """
        if policy_name and policy_name in self._policies:
            policies_to_eval = {policy_name: self._policies[policy_name]}
        else:
            policies_to_eval = dict(sorted(self._policies.items()))

        for _pname, policy in policies_to_eval.items():
            rules = sorted(
                policy.get("rules", []),
                key=lambda r: r.get("priority", 999),
            )
            for rule in rules:
                if self._evaluate_conditions(rule["conditions"], review_data):
                    return Disposition(rule["disposition"])

        # Default: HUMAN review (safe conservative default per CONTEXT.md)
        return Disposition.HUMAN

    def _evaluate_conditions(self, conditions: dict, data: dict) -> bool:
        """Evaluate an AND/OR condition block against review data."""
        operator = conditions["operator"]
        checks = conditions["checks"]

        if operator == "AND":
            return all(self._evaluate_check(ch, data) for ch in checks)
        elif operator == "OR":
            return any(self._evaluate_check(ch, data) for ch in checks)
        return False

    def _evaluate_check(self, check: dict, data: dict) -> bool:
        """Evaluate a single condition check.

        Supports dotted field access (e.g. ``metadata.flagged`` resolves to
        ``data["metadata"]["flagged"]``).
        """
        field: str = check["field"]
        op: str = check["operator"]
        expected = check["value"]

        # Resolve dotted field path
        value = data
        for part in field.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return False  # Field not found -> condition fails

        # Evaluate operator
        if op == "equals":
            return value == expected
        elif op == "not_equals":
            return value != expected
        elif op == "greater_than":
            return value > expected
        elif op == "less_than":
            return value < expected
        elif op == "greater_than_or_equal":
            return value >= expected
        elif op == "less_than_or_equal":
            return value <= expected
        elif op == "contains":
            return expected in value if isinstance(value, (str, list)) else False
        elif op == "in":
            return value in expected if isinstance(expected, (list, tuple)) else False
        return False

    # -- Management ----------------------------------------------------------

    def get_policy(self, name: str) -> dict | None:
        """Return a loaded policy by name, or None."""
        return self._policies.get(name)

    def list_policies(self) -> list[str]:
        """Return sorted list of loaded policy names."""
        return sorted(self._policies.keys())

    def remove_policy(self, name: str) -> bool:
        """Remove a loaded policy. Returns True if found and removed."""
        if name in self._policies:
            del self._policies[name]
            return True
        return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    """Return the global PolicyEngine singleton."""
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine
