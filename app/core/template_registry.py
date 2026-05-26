"""YAML template registry with JSON Schema validation and source_system + phase resolution.

Loads YAML template configuration files, validates them against a JSON Schema,
and resolves review UI layouts by source_system + phase. Mirrors the PolicyEngine
pattern from app/core/policy.py for consistency.

Threat mitigations:
- T-23-01: All include paths validated to start with "partials/" prefix.
- T-23-02: Only yaml.safe_load() is used (never yaml.load).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml


# ---------------------------------------------------------------------------
# JSON Schema for template YAML validation
# ---------------------------------------------------------------------------

TEMPLATE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "version", "source_system", "templates"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "pattern": r"^\d+\.\d+$"},
        "source_system": {"type": "string", "minLength": 1},
        "templates": {
            "type": "object",
            "minProperties": 1,
            "patternProperties": {
                "^[a-zA-Z0-9_-]+$": {
                    "type": "object",
                    "properties": {
                        "desktop": {
                            "type": "object",
                            "properties": {
                                "decision_panel": {"type": "string"},
                                "media_player": {"type": "string"},
                                "show_scores": {"type": "boolean"},
                                "show_candidates": {"type": "boolean"},
                                "candidate_layout": {
                                    "type": "string",
                                    "enum": ["grid", "side-by-side", "stacked"],
                                },
                            },
                        },
                        "mobile": {
                            "type": "object",
                            "properties": {
                                "card_variant": {"type": "string"},
                                "show_scores": {"type": "boolean"},
                            },
                        },
                        "_allowed_partials": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TemplateError(Exception):
    """Base exception for template errors."""


class TemplateValidationError(TemplateError):
    """Raised when a template config fails YAML or JSON Schema validation."""


# ---------------------------------------------------------------------------
# TemplateConfig dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplateConfig:
    """Resolved template configuration for a specific source_system + phase.

    Provides defaults that match the standard review layout when no
    template overrides are specified.
    """

    desktop_decision_panel: str = "partials/_decision_panel.html"
    desktop_media_player: str = "partials/_media_player.html"
    mobile_card_variant: str = "default"
    show_scores: bool = False
    show_candidates: bool = True
    candidate_layout: str = "grid"
    extra_fields: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TemplateRegistry
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """In-memory template registry.

    Template YAML configs are loaded from files or directories, validated
    against TEMPLATE_JSON_SCHEMA, and stored indexed by source_system for
    fast lookup via resolve().
    """

    def __init__(self) -> None:
        self._templates: dict[str, dict] = {}  # source_system -> parsed templates dict

    # -- Loading / Validation ------------------------------------------------

    def validate_template(self, yaml_content: str) -> dict:
        """Parse and validate YAML template content.

        Returns the parsed dict on success.
        Raises TemplateValidationError on invalid YAML or schema mismatch.
        """
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as exc:
            raise TemplateValidationError(f"Invalid YAML syntax: {exc}") from exc

        if not isinstance(data, dict):
            raise TemplateValidationError(
                "Template YAML must be a mapping (object), got "
                f"{type(data).__name__}"
            )

        try:
            jsonschema.validate(instance=data, schema=TEMPLATE_JSON_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise TemplateValidationError(
                f"Template schema validation failed: {exc.message}"
            ) from exc

        # Path security check: all include paths must start with "partials/"
        self._validate_include_paths(data)

        return data

    def _validate_include_paths(self, data: dict) -> None:
        """Ensure all decision_panel and media_player paths start with 'partials/'."""
        for _phase_name, phase_config in data.get("templates", {}).items():
            desktop = phase_config.get("desktop", {})
            for path_field in ("decision_panel", "media_player"):
                value = desktop.get(path_field)
                if value is not None and not value.startswith("partials/"):
                    raise TemplateValidationError(
                        f"Path traversal detected: {path_field}='{value}' must start "
                        "with 'partials/' prefix"
                    )

    def load_from_file(self, filepath: str) -> dict:
        """Load template config from a YAML file path."""
        with open(filepath, "r") as fh:
            content = fh.read()
        data = self.validate_template(content)
        source_system = data["source_system"]
        self._templates[source_system] = data["templates"]
        return data

    def load_from_directory(self, dirpath: str) -> list[str]:
        """Load all .yaml files from a directory. Returns list of loaded names."""
        loaded: list[str] = []
        for filename in sorted(Path(dirpath).glob("*.yaml")):
            data = self.load_from_file(str(filename))
            loaded.append(data["name"])
        return loaded

    # -- Resolution ----------------------------------------------------------

    def resolve(self, source_system: str, phase: str | None = None) -> TemplateConfig:
        """Resolve a TemplateConfig for the given source_system + phase.

        Fallback chain:
        1. source_system -> phase (exact match)
        2. source_system -> "_default" (source-level fallback)
        3. Global default TemplateConfig()
        """
        source_templates = self._templates.get(source_system)
        if source_templates is None:
            return TemplateConfig()

        # Try exact phase match
        if phase and phase in source_templates:
            return self._build_config(source_templates[phase])

        # Try source-level default
        if "_default" in source_templates:
            return self._build_config(source_templates["_default"])

        # Global default
        return TemplateConfig()

    def _build_config(self, phase_data: dict) -> TemplateConfig:
        """Build a TemplateConfig from a phase's YAML data."""
        desktop = phase_data.get("desktop", {})
        mobile = phase_data.get("mobile", {})

        return TemplateConfig(
            desktop_decision_panel=desktop.get(
                "decision_panel", "partials/_decision_panel.html"
            ),
            desktop_media_player=desktop.get(
                "media_player", "partials/_media_player.html"
            ),
            mobile_card_variant=mobile.get("card_variant", "default"),
            show_scores=desktop.get("show_scores", False),
            show_candidates=desktop.get("show_candidates", True),
            candidate_layout=desktop.get("candidate_layout", "grid"),
            extra_fields={
                k: v
                for k, v in phase_data.items()
                if k not in ("desktop", "mobile", "_allowed_partials")
            },
        )

    # -- Management ----------------------------------------------------------

    def list_templates(self) -> list[str]:
        """Return sorted list of loaded source_system names."""
        return sorted(self._templates.keys())


# ---------------------------------------------------------------------------
# Source system derivation
# ---------------------------------------------------------------------------

# Prefix mapping for project_id -> source_system convention
_PROJECT_PREFIX_MAP: dict[str, str] = {
    "movie-agent": "kais-movie-agent",
    "gold-team": "kais-gold-team",
}


def derive_source_system(shot_card: Any) -> str:
    """Derive the source_system from a ShotCard.

    Resolution order:
    1. shot_card.narrative_context["source_system"] (if present and non-empty)
    2. shot_card.project_id prefix convention (movie-agent -> kais-movie-agent, etc.)
    3. Fallback: "unknown"
    """
    # Try narrative_context first
    narrative_context = getattr(shot_card, "narrative_context", None) or {}
    source = narrative_context.get("source_system")
    if source:
        return source

    # Try project_id prefix convention
    project_id = getattr(shot_card, "project_id", "") or ""
    for prefix, system in _PROJECT_PREFIX_MAP.items():
        if project_id.startswith(prefix):
            return system

    return "unknown"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: TemplateRegistry | None = None


def get_template_registry() -> TemplateRegistry:
    """Return the global TemplateRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry
