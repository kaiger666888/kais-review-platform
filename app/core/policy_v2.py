"""V2 ShotCard-aware policy engine with policy stacking.

Extends V1 PolicyEngine to accept Shot Card objects as input, converting them
to flat evaluation dicts that leverage the existing dotted-field resolver.
Adds policy stacking (global -> project -> temporary, last-layer match wins)
and returns a PolicyResult tracking disposition, matched rule, commit SHA,
and layers evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.policy import PolicyEngine
from app.models.shot_card import RoutingDecision


# ---------------------------------------------------------------------------
# PolicyResult
# ---------------------------------------------------------------------------


@dataclass
class PolicyResult:
    """Outcome of a policy evaluation with full tracking metadata."""

    disposition: RoutingDecision
    policy_commit_sha: str | None = None
    matched_rule: str | None = None
    stack_layers_evaluated: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ShotCardPolicyEngine
# ---------------------------------------------------------------------------


class ShotCardPolicyEngine(PolicyEngine):
    """Policy engine that understands Shot Card structure.

    Extends V1 PolicyEngine with:
    - _shot_card_to_eval_dict() to convert ShotCard models/dicts to flat eval dicts
    - evaluate_shot_card() for single-policy evaluation
    - evaluate_with_stack() for multi-layer policy stacking
    """

    # -- Conversion ----------------------------------------------------------

    @staticmethod
    def _shot_card_to_eval_dict(shot_card) -> dict:
        """Convert a ShotCard model instance or dict to a flat evaluation dict.

        The resulting dict uses dotted keys that the V1 _evaluate_check()
        dotted-path resolver can traverse, e.g. ``narrative_context.scene``
        resolves to ``result["narrative_context"]["scene"]``.
        """
        # Accept both MagicMock/dict/SQLAlchemy model via attribute access
        if isinstance(shot_card, dict):
            project_id = shot_card.get("project_id", "")
            shot_id = shot_card.get("shot_id", "")
            audit_status = shot_card.get("audit_status", "")
            routing_decision = shot_card.get("routing_decision")
            narrative_context = shot_card.get("narrative_context") or {}
            visual_bundle = shot_card.get("visual_bundle")
            audio_bundle = shot_card.get("audio_bundle")
        else:
            project_id = getattr(shot_card, "project_id", "")
            shot_id = getattr(shot_card, "shot_id", "")
            audit_status = getattr(shot_card, "audit_status", "")
            routing_decision = getattr(shot_card, "routing_decision", None)
            narrative_context = getattr(shot_card, "narrative_context", None) or {}
            visual_bundle = getattr(shot_card, "visual_bundle", None)
            audio_bundle = getattr(shot_card, "audio_bundle", None)

        result: dict = {
            "project_id": project_id,
            "shot_id": shot_id,
            "audit_status": audit_status,
        }

        if routing_decision is not None:
            result["routing_decision"] = routing_decision

        if isinstance(narrative_context, dict):
            result["narrative_context"] = narrative_context

        if visual_bundle is not None:
            result["visual_bundle"] = visual_bundle

        if audio_bundle is not None:
            result["audio_bundle"] = audio_bundle

        return result

    # -- Single-policy evaluation -------------------------------------------

    def evaluate_shot_card(self, shot_card, policy_name: str | None = None) -> PolicyResult:
        """Evaluate a ShotCard against loaded policies.

        Converts the ShotCard to a flat eval dict and delegates to the
        V1 ``evaluate()`` method.
        """
        eval_dict = self._shot_card_to_eval_dict(shot_card)
        disposition = self.evaluate(eval_dict, policy_name=policy_name)

        # Try to determine which rule matched (best-effort)
        matched_rule = self._find_matched_rule(eval_dict, policy_name)

        return PolicyResult(
            disposition=RoutingDecision(disposition.value)
            if not isinstance(disposition, RoutingDecision)
            else disposition,
            matched_rule=matched_rule,
            stack_layers_evaluated=["loaded"],
        )

    # -- Policy stacking evaluation -----------------------------------------

    def evaluate_with_stack(
        self,
        shot_card_or_dict,
        policies_by_layer: dict[str, list[dict]],
        project_id: str | None = None,
    ) -> PolicyResult:
        """Evaluate a ShotCard against stacked policy layers.

        Layer order: global -> project -> temporary.
        Within each layer, rules are sorted by priority (ascending), first match wins.
        Last layer's match wins overall (later layer overrides earlier layers).

        Args:
            shot_card_or_dict: A ShotCard model, MagicMock, or dict.
            policies_by_layer: ``{"global": [policy_dict, ...], "project": [...], "temporary": [...]}``
            project_id: Optional project ID for context (not used for filtering here).

        Returns:
            PolicyResult with full tracking metadata.
        """
        eval_dict = self._shot_card_to_eval_dict(shot_card_or_dict)

        layer_order = ["global", "project", "temporary"]
        final_disposition: RoutingDecision | None = None
        final_matched_rule: str | None = None
        layers_evaluated: list[str] = []

        for layer_name in layer_order:
            policies = policies_by_layer.get(layer_name, [])
            if not policies:
                continue

            layers_evaluated.append(layer_name)

            for policy in policies:
                rules = sorted(
                    policy.get("rules", []),
                    key=lambda r: r.get("priority", 999),
                )
                for rule in rules:
                    if self._evaluate_conditions(rule["conditions"], eval_dict):
                        final_disposition = RoutingDecision(rule["disposition"])
                        final_matched_rule = rule["name"]
                        break  # first match in this policy
                # Continue checking other policies in same layer
                # (they may have higher-priority rules)
                # Actually, we should check all policies in the layer and
                # use the one with the highest priority (lowest number) that matches.
                # Let me restructure: collect all matching rules in this layer.

            # Re-evaluate: collect all matches from all policies in this layer,
            # then pick the one with the lowest priority number.
            layer_match = self._find_layer_match(policies, eval_dict)
            if layer_match is not None:
                final_disposition = layer_match[0]
                final_matched_rule = layer_match[1]

        if final_disposition is None:
            final_disposition = RoutingDecision.HUMAN

        return PolicyResult(
            disposition=final_disposition,
            matched_rule=final_matched_rule,
            stack_layers_evaluated=layers_evaluated,
        )

    # -- Internal helpers ----------------------------------------------------

    def _find_layer_match(
        self, policies: list[dict], eval_dict: dict
    ) -> tuple[RoutingDecision, str] | None:
        """Find the best matching rule across all policies in a layer.

        Returns (disposition, rule_name) for the lowest-priority match, or None.
        """
        best_match: tuple[int, RoutingDecision, str] | None = None

        for policy in policies:
            rules = sorted(
                policy.get("rules", []),
                key=lambda r: r.get("priority", 999),
            )
            for rule in rules:
                if self._evaluate_conditions(rule["conditions"], eval_dict):
                    priority = rule.get("priority", 999)
                    if best_match is None or priority < best_match[0]:
                        best_match = (
                            priority,
                            RoutingDecision(rule["disposition"]),
                            rule["name"],
                        )

        if best_match is not None:
            return (best_match[1], best_match[2])
        return None

    def _find_matched_rule(
        self, eval_dict: dict, policy_name: str | None = None
    ) -> str | None:
        """Best-effort find which rule matched in loaded V1 policies."""
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
