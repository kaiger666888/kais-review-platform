"""Integration tests for template-aware rendering in desktop and mobile paths.

Tests that:
1. Desktop shot-card-detail renders template-selected partials via wrapper
2. Movie-agent shot cards show candidate grid elements
3. Gold-team shot cards show risk assessment elements
4. Unknown source_system falls back to default decision panel
5. Mobile API returns template_config in MobileShotCardBundle
"""

import os

os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-min-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest
from pathlib import Path
from unittest.mock import MagicMock

import app.core.template_registry as tr_mod
from app.core.template_registry import (
    TemplateConfig,
    TemplateRegistry,
    derive_source_system,
)
from app.api.v1.mobile import _shot_card_to_bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOVIE_AGENT_YAML = """\
name: movie-agent-templates
version: "1.0"
source_system: kais-movie-agent
templates:
  art-direction:
    desktop:
      decision_panel: partials/_template_candidate_grid.html
      media_player: partials/_media_player.html
      show_scores: true
      show_candidates: true
      candidate_layout: side-by-side
    mobile:
      card_variant: candidate-swipe
      show_scores: true
  _default:
    desktop:
      decision_panel: partials/_decision_panel.html
      media_player: partials/_media_player.html
      show_scores: false
      show_candidates: true
      candidate_layout: grid
    mobile:
      card_variant: default
"""

_GOLD_TEAM_YAML = """\
name: gold-team-templates
version: "1.0"
source_system: kais-gold-team
templates:
  task-parameter:
    desktop:
      decision_panel: partials/_template_risk_assessment.html
      media_player: partials/_media_player.html
      show_scores: false
      show_candidates: false
    mobile:
      card_variant: risk-assessment
  _default:
    desktop:
      decision_panel: partials/_decision_panel.html
      media_player: partials/_media_player.html
    mobile:
      card_variant: default
"""

_DEFAULT_YAML = """\
name: default-template
version: "1.0"
source_system: default
templates:
  _default:
    desktop:
      decision_panel: partials/_decision_panel.html
      media_player: partials/_media_player.html
      show_candidates: true
      show_scores: false
      candidate_layout: grid
    mobile:
      card_variant: default
      show_scores: false
"""


def _load_test_registry() -> TemplateRegistry:
    """Create and populate a TemplateRegistry with test YAML configs."""
    import yaml

    registry = TemplateRegistry()
    for content in (_MOVIE_AGENT_YAML, _GOLD_TEAM_YAML, _DEFAULT_YAML):
        data = yaml.safe_load(content)
        registry.validate_template(content)
        registry._templates[data["source_system"]] = data["templates"]
    return registry


def _make_mock_shot_card(
    shot_id: str = "shot-001",
    project_id: str = "movie-agent-proj-001",
    narrative_context: dict | None = None,
    visual_bundle: dict | None = None,
    audit_status: str = "awaiting_audit",
    routing_decision: str | None = None,
) -> MagicMock:
    """Create a mock ShotCard ORM object for testing."""
    nc = narrative_context or {
        "scene": "scene-01",
        "shot_number": 1,
        "emotion_curve": "rising",
        "continuity_tags": ["day", "interior"],
    }
    vb = visual_bundle or {
        "keyframes": {
            "first": {"url": "https://example.com/first.jpg", "hash": "abc123", "node": "gen-01"},
            "last": {"url": "https://example.com/last.jpg", "hash": "def456", "node": "gen-01"},
        },
        "video_clip": {"url": "https://example.com/video.mp4", "duration": 3.5, "node": "render-01"},
        "prompt": "A dramatic scene",
        "candidates": [
            {
                "candidate_id": "cand-1",
                "keyframes": {"first": {"url": "https://example.com/c1.jpg", "hash": "h1", "node": "gen-a"}},
                "score": 0.85,
            },
            {
                "candidate_id": "cand-2",
                "keyframes": {"first": {"url": "https://example.com/c2.jpg", "hash": "h2", "node": "gen-b"}},
                "score": 0.62,
            },
        ],
    }

    card = MagicMock()
    card.shot_id = shot_id
    card.project_id = project_id
    card.narrative_context = nc
    card.visual_bundle = vb
    card.audio_bundle = {"status": "pending"}
    card.audit_status = audit_status
    card.routing_decision = routing_decision
    return card


# ---------------------------------------------------------------------------
# Test 1: Movie-agent shot card detail returns candidate grid HTML
# ---------------------------------------------------------------------------


class TestMovieAgentDesktopRendering:
    def test_movie_agent_art_direction_resolves_candidate_grid(self):
        """Movie-agent art-direction should resolve to candidate grid template."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            project_id="movie-agent-proj-001",
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
                "phase": "art-direction",
            },
        )

        source = derive_source_system(card)
        assert source == "kais-movie-agent"

        tc = registry.resolve(source, card.narrative_context.get("phase"))
        assert tc.desktop_decision_panel == "partials/_template_candidate_grid.html"
        assert tc.show_candidates is True
        assert tc.show_scores is True
        assert tc.candidate_layout == "side-by-side"

    def test_movie_agent_mobile_bundle_has_template_config(self):
        """Mobile API bundle for movie-agent should contain template_config."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            project_id="movie-agent-proj-001",
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
                "phase": "art-direction",
            },
        )

        bundle = _shot_card_to_bundle(card)
        assert bundle.template_config is not None
        assert bundle.template_config["card_variant"] == "candidate-swipe"
        assert bundle.template_config["show_scores"] is True
        assert bundle.template_config["show_candidates"] is True


# ---------------------------------------------------------------------------
# Test 2: Gold-team shot card detail returns risk assessment HTML
# ---------------------------------------------------------------------------


class TestGoldTeamDesktopRendering:
    def test_gold_team_task_parameter_resolves_risk_assessment(self):
        """Gold-team task-parameter should resolve to risk assessment template."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            project_id="gold-team-task-001",
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "neutral",
                "phase": "task-parameter",
                "task_type": "render_check",
                "task_params": {"quality": "high", "resolution": "4K"},
                "risk_score": 0.75,
            },
        )

        source = derive_source_system(card)
        assert source == "kais-gold-team"

        tc = registry.resolve(source, card.narrative_context.get("phase"))
        assert tc.desktop_decision_panel == "partials/_template_risk_assessment.html"
        assert tc.show_candidates is False
        assert tc.mobile_card_variant == "risk-assessment"


# ---------------------------------------------------------------------------
# Test 3: Unknown source_system returns default decision panel
# ---------------------------------------------------------------------------


class TestUnknownSourceFallback:
    def test_unknown_source_returns_default_template(self):
        """Unknown source_system should fall back to default decision panel."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            project_id="random-project-999",
            narrative_context={
                "scene": "scene-02",
                "shot_number": 3,
                "emotion_curve": "flat",
            },
        )

        source = derive_source_system(card)
        assert source == "unknown"

        tc = registry.resolve(source, "some-phase")
        assert tc.desktop_decision_panel == "partials/_decision_panel.html"
        assert tc.show_candidates is True


# ---------------------------------------------------------------------------
# Test 4: Mobile API returns template_config in MobileShotCardBundle
# ---------------------------------------------------------------------------


class TestMobileTemplateConfig:
    def test_mobile_bundle_includes_template_config(self):
        """_shot_card_to_bundle should include template_config dict."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            project_id="gold-team-task-005",
            narrative_context={
                "scene": "scene-03",
                "shot_number": 5,
                "emotion_curve": "tense",
                "phase": "task-parameter",
                "risk_score": 0.42,
            },
        )

        bundle = _shot_card_to_bundle(card)
        assert bundle.template_config is not None
        assert "card_variant" in bundle.template_config
        assert bundle.template_config["card_variant"] == "risk-assessment"

    def test_mobile_bundle_unknown_source_has_default_config(self):
        """Unknown source_system mobile bundle should have default template_config."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            project_id="unknown-proj-999",
            narrative_context={
                "scene": "scene-04",
                "shot_number": 2,
                "emotion_curve": "calm",
            },
        )

        bundle = _shot_card_to_bundle(card)
        assert bundle.template_config is not None
        assert bundle.template_config["card_variant"] == "default"


# ---------------------------------------------------------------------------
# Test 5: Template wrapper renders include path from TemplateConfig
# ---------------------------------------------------------------------------


class TestTemplateWrapperRendering:
    def test_wrapper_template_file_exists(self):
        """Template wrapper file must exist."""
        wrapper_path = Path("app/templates/partials/_template_wrapper.html")
        assert wrapper_path.exists(), "Template wrapper file must exist"

    def test_candidate_grid_partial_exists(self):
        """Candidate grid partial must exist."""
        candidate_path = Path("app/templates/partials/_template_candidate_grid.html")
        assert candidate_path.exists(), "Candidate grid partial must exist"

    def test_risk_assessment_partial_exists(self):
        """Risk assessment partial must exist."""
        risk_path = Path("app/templates/partials/_template_risk_assessment.html")
        assert risk_path.exists(), "Risk assessment partial must exist"

    def test_wrapper_with_default_config_includes_decision_panel(self):
        """Default TemplateConfig should reference standard decision panel."""
        tc = TemplateConfig()  # all defaults
        assert tc.desktop_decision_panel == "partials/_decision_panel.html"

    def test_wrapper_contains_dynamic_include(self):
        """Wrapper template should contain dynamic include for template.desktop_decision_panel."""
        wrapper_path = Path("app/templates/partials/_template_wrapper.html")
        if wrapper_path.exists():
            content = wrapper_path.read_text()
            assert "template.desktop_decision_panel" in content
        else:
            pytest.fail("Template wrapper file must exist")

    def test_candidate_grid_contains_candidate_elements(self):
        """Candidate grid partial should contain candidate-related HTML elements."""
        candidate_path = Path("app/templates/partials/_template_candidate_grid.html")
        if candidate_path.exists():
            content = candidate_path.read_text()
            assert "candidate" in content.lower()
        else:
            pytest.fail("Candidate grid partial must exist")

    def test_risk_assessment_contains_risk_score(self):
        """Risk assessment partial should contain risk_score reference."""
        risk_path = Path("app/templates/partials/_template_risk_assessment.html")
        if risk_path.exists():
            content = risk_path.read_text()
            assert "risk_score" in content
        else:
            pytest.fail("Risk assessment partial must exist")
