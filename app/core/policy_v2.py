"""Enhanced policy engine for Shot Card evaluation with policy stacking.

Extends the V1 PolicyEngine to accept ShotCard model objects, evaluate
them against layered policies (global, project, temporary), and return
rich PolicyResult objects with provenance tracking.

V1 PolicyEngine (app/core/policy.py) is kept completely untouched.
ShotCardPolicyEngine inherits from it and adds Shot Card-specific methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.policy import PolicyEngine
from app.models.schemas import Disposition


# ---------------------------------------------------------------------------
# PolicyResult — rich evaluation result with provenance
# ---------------------------------------------------------------------------


@dataclass
class PolicyResult:
    """Result of a policy evaluation with full tracking information."""

    disposition: Disposition
    policy_commit_sha: str | None = None
    matched_rule: str | None = None
    stack_layers_evaluated: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ShotCardPolicyEngine
# ---------------------------------------------------------------------------


class ShotCardPolicyEngine(PolicyEngine):
    """Enhanced policy engine that accepts ShotCard objects.

    Extends V1 PolicyEngine with:
    - _shot_card_to_eval_dict() — converts ShotCard to flat evaluation dict
    - evaluate_shot_card() — evaluates a ShotCard against loaded policies
    - evaluate_with_stack() — evaluates with layered policy stacking
    - load_policies_from_layer() — batch loads policies for a named layer
    """

    # -- Conversion ----------------------------------------------------------

    @staticmethod
    def _shot_card_to_eval_dict(shot_card) -> dict:
        """Convert a ShotCard model (or dict) to a flat evaluation dict.

        The result preserves nested structure so that dotted-path access
        (e.g. narrative_context.scene) works via the inherited
        _evaluate_check() method.

        Args:
            shot_card: A ShotCard SQLAlchemy model, MagicMock, or plain dict.

        Returns:
            Flat dict suitable for PolicyEngine.evaluate().
        """
        if isinstance(shot_card, dict):
            data = shot_card
        else:
            # Build from attribute access (works with models and MagicMocks)
            data = {
                "shot_id": getattr(shot_card, "shot_id", None),
                "project_id": getattr(shot_card, "project_id", None),
                "audit_status": getattr(shot_card, "audit_status", None),
                "narrative_context": getattr(shot_card, "narrative_context", None),
                "visual_bundle": getattr(shot_card, "visual_bundle", None),
                "audio_bundle": getattr(shot_card, "audio_bundle", None),
                "routing_decision": getattr(shot_card, "routing_decision", None),
            }

        return data

    # -- Shot Card Evaluation ------------------------------------------------

    def evaluate_shot_card(
        self, shot_card, policy_name: str | None = None
    ) -> PolicyResult:
        """Evaluate a ShotCard against loaded policies.

        Converts the ShotCard to an eval dict, delegates to parent
        evaluate(), and returns a PolicyResult with tracking info.

        Args:
            shot_card: ShotCard model, MagicMock, or dict.
            policy_name: Optional specific policy to evaluate.

        Returns:
            PolicyResult with disposition, matched rule, and layer info.
        """
        eval_dict = self._shot_card_to_eval_dict(shot_card)
        disposition = self.evaluate(eval_dict, policy_name=policy_name)

        # Find which rule matched by re-evaluating with tracking
        matched_rule = self._find_matched_rule(eval_dict, policy_name)

        return PolicyResult(
            disposition=disposition,
            matched_rule=matched_rule,
            stack_layers_evaluated=["direct"],
        )

    def _find_matched_rule(
        self, eval_dict: dict, policy_name: str | None = None
    ) -> str | None:
        """Find which rule matched the evaluation data.

        Re-runs evaluation logic to identify the specific rule name.
        """
        if policy_name and policy_name in self._policies:
            policies_to_check = {policy_name: self._policies[policy_name]}
        else:
            policies_to_check = dict(sorted(self._policies.items()))

        for _pname, policy in policies_to_check.items():
            rules = sorted(
                policy.get("rules", []),
                key=lambda r: r.get("priority", 999),
            )
            for rule in rules:
                if self._evaluate_conditions(rule["conditions"], eval_dict):
                    return rule["name"]

        return None

    # -- Policy Stacking -----------------------------------------------------

    def evaluate_with_stack(
        self,
        shot_card,
        policies_by_layer: dict[str, list[str]],
        policy_commit_sha: str | None = None,
    ) -> PolicyResult:
        """Evaluate a ShotCard against stacked policy layers.

        Layers are evaluated in order: global -> project -> temporary.
        Within each layer, rules are sorted by priority (ascending) and
        the first matching rule wins for that layer. The last layer's
        match wins overall (later layer overrides earlier).

        Args:
            shot_card: ShotCard model, MagicMock, or dict.
            policies_by_layer: Mapping of layer name to list of policy names
                in that layer. E.g. {"global": ["global_routing"],
                "project": ["project_strict"]}.
            policy_commit_sha: Optional Git commit SHA for provenance.

        Returns:
            PolicyResult with full tracking information.
        """
        eval_dict = self._shot_card_to_eval_dict(shot_card)

        # Layer order determines precedence (later overrides earlier)
        layer_order = ["global", "project", "temporary"]
        final_disposition = Disposition.HUMAN  # Safe default
        final_matched_rule: str | None = None
        layers_evaluated: list[str] = []

        for layer_name in layer_order:
            policy_names = policies_by_layer.get(layer_name, [])
            if not policy_names:
                continue

            layers_evaluated.append(layer_name)

            # Evaluate all policies in this layer
            for pname in policy_names:
                if pname not in self._policies:
                    continue

                policy = self._policies[pname]
                rules = sorted(
                    policy.get("rules", []),
                    key=lambda r: r.get("priority", 999),
                )

                for rule in rules:
                    if self._evaluate_conditions(rule["conditions"], eval_dict):
                        final_disposition = Disposition(rule["disposition"])
                        final_matched_rule = rule["name"]
                        break  # First match wins within a policy

        return PolicyResult(
            disposition=final_disposition,
            policy_commit_sha=policy_commit_sha,
            matched_rule=final_matched_rule,
            stack_layers_evaluated=layers_evaluated,
        )

    # -- Batch Loading -------------------------------------------------------

    def load_policies_from_layer(
        self, yaml_contents: dict[str, str], layer_name: str
    ) -> list[str]:
        """Batch-load multiple YAML policies for a named layer.

        Args:
            yaml_contents: Mapping of policy name to YAML content string.
            layer_name: Layer name (for logging purposes).

        Returns:
            List of successfully loaded policy names.
        """
        loaded: list[str] = []
        for name, content in yaml_contents.items():
            self.load_policy(name, content)
            loaded.append(name)
        return loaded
