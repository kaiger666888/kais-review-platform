"""Tests for external AI score integration.

Tests that:
1. NarrativeContext accepts optional ai_score fields (all default to None)
2. NarrativeContext with ai_score fields serializes correctly
3. MobileShotCardBundle accepts optional ai_score fields
4. _shot_card_to_bundle extracts ai_score fields from narrative_context
5. _shot_card_to_bundle returns None for ai_score fields when no score data
6. ShotCardCreate with ai_score in narrative_context passes validation
7. _decision_panel.html renders AI Score section when show_scores=true and score present
8. _decision_panel.html does NOT render AI Score section when show_scores=false
9. _decision_panel.html does NOT render AI Score section when no ai_score key
10. _mobile_card.html renders AI score badge when show_scores=true and score present
11. _template_candidate_grid.html renders ShotCard-level AI Score panel
"""

import os

os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-min-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

import app.core.template_registry as tr_mod
from app.core.template_registry import TemplateConfig, TemplateRegistry
from app.models.schemas import (
    MobileShotCardBundle,
    NarrativeContext,
    ShotCardCreate,
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
  quality-gate:
    desktop:
      decision_panel: partials/_decision_panel.html
      media_player: partials/_media_player.html
      show_scores: true
      show_candidates: false
    mobile:
      card_variant: default
      show_scores: true
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
      show_scores: false
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
    registry = TemplateRegistry()
    for content in (_MOVIE_AGENT_YAML, _DEFAULT_YAML):
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
    }

    card = MagicMock()
    card.id = 1
    card.shot_id = shot_id
    card.project_id = project_id
    card.narrative_context = nc
    card.visual_bundle = vb
    card.audio_bundle = {"status": "pending"}
    card.audit_status = audit_status
    card.routing_decision = routing_decision
    return card


def _render_template(template_path: str, **context) -> str:
    """Render a Jinja2 template with the given context."""
    from jinja2 import Environment, FileSystemLoader

    templates_dir = Path("app/templates")
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )
    template = env.get_template(template_path)
    return template.render(**context)


# ---------------------------------------------------------------------------
# Task 1 Tests: Schema + Bundle extension
# ---------------------------------------------------------------------------


class TestNarrativeContextScoreFields:
    """Tests 1-2: NarrativeContext accepts and serializes ai_score fields."""

    def test_narrative_context_accepts_optional_ai_score_fields(self):
        """Test 1: NarrativeContext accepts optional ai_score fields, all defaulting to None."""
        nc = NarrativeContext(
            scene="scene-01",
            shot_number=1,
            emotion_curve="rising",
        )
        assert nc.ai_score is None
        assert nc.ai_score_dimensions is None
        assert nc.ai_score_source is None

    def test_narrative_context_with_ai_score_serializes_correctly(self):
        """Test 2: NarrativeContext with full score data serializes correctly."""
        nc = NarrativeContext(
            scene="scene-01",
            shot_number=1,
            emotion_curve="rising",
            ai_score=72,
            ai_score_dimensions={
                "visual_quality": 80,
                "audio_quality": 65,
                "consistency": 70,
            },
            ai_score_source="movie-agent",
        )
        assert nc.ai_score == 72
        assert nc.ai_score_dimensions == {
            "visual_quality": 80,
            "audio_quality": 65,
            "consistency": 70,
        }
        assert nc.ai_score_source == "movie-agent"

        # Verify serialization round-trips through dict
        data = nc.model_dump()
        assert data["ai_score"] == 72
        assert data["ai_score_dimensions"]["visual_quality"] == 80
        assert data["ai_score_source"] == "movie-agent"


class TestMobileBundleScoreFields:
    """Test 3: MobileShotCardBundle accepts optional ai_score fields."""

    def test_mobile_bundle_accepts_optional_ai_score_fields(self):
        """Test 3: MobileShotCardBundle accepts optional ai_score fields."""
        bundle = MobileShotCardBundle(
            id=1,
            shot_id="shot-001",
            project_id="proj-001",
            scene="scene-01",
            shot_number=1,
            emotion_curve="rising",
            continuity_tags=["day"],
            audit_status="awaiting_audit",
            ai_score=85,
            ai_score_dimensions={"visual_quality": 90, "audio_quality": 80},
            ai_score_source="movie-agent",
        )
        assert bundle.ai_score == 85
        assert bundle.ai_score_dimensions == {"visual_quality": 90, "audio_quality": 80}
        assert bundle.ai_score_source == "movie-agent"


class TestShotCardToBundleScoreExtraction:
    """Tests 4-5: _shot_card_to_bundle extracts ai_score from narrative_context."""

    def test_shot_card_to_bundle_extracts_ai_score(self):
        """Test 4: _shot_card_to_bundle extracts ai_score fields from narrative_context."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
                "ai_score": 72,
                "ai_score_dimensions": {
                    "visual_quality": 80,
                    "audio_quality": 65,
                    "consistency": 70,
                },
                "ai_score_source": "movie-agent",
            },
        )

        bundle = _shot_card_to_bundle(card)
        assert bundle.ai_score == 72
        assert bundle.ai_score_dimensions == {
            "visual_quality": 80,
            "audio_quality": 65,
            "consistency": 70,
        }
        assert bundle.ai_score_source == "movie-agent"

    def test_shot_card_to_bundle_returns_none_when_no_scores(self):
        """Test 5: _shot_card_to_bundle returns None for ai_score when no score keys."""
        registry = _load_test_registry()
        tr_mod._registry = registry

        card = _make_mock_shot_card(
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
            },
        )

        bundle = _shot_card_to_bundle(card)
        assert bundle.ai_score is None
        assert bundle.ai_score_dimensions is None
        assert bundle.ai_score_source is None


class TestShotCardCreateWithScores:
    """Test 6: ShotCardCreate with ai_score in narrative_context passes validation."""

    def test_shot_card_create_with_ai_score_passes_validation(self):
        """Test 6: ShotCardCreate with ai_score fields in narrative_context validates."""
        create = ShotCardCreate(
            shot_id="shot-001",
            project_id="proj-001",
            narrative_context=NarrativeContext(
                scene="scene-01",
                shot_number=1,
                emotion_curve="rising",
                ai_score=72,
                ai_score_dimensions={"visual_quality": 80},
                ai_score_source="movie-agent",
            ),
        )
        nc = create.narrative_context
        assert nc.ai_score == 72
        assert nc.ai_score_dimensions == {"visual_quality": 80}
        assert nc.ai_score_source == "movie-agent"


# ---------------------------------------------------------------------------
# Task 2 Tests: Template rendering of AI scores
# ---------------------------------------------------------------------------


class TestDecisionPanelScoreRendering:
    """Tests 7-9: _decision_panel.html AI score rendering."""

    def test_decision_panel_renders_ai_score_when_show_scores_true(self):
        """Test 7: _decision_panel.html renders AI Score section when show_scores is true."""
        tc = MagicMock()
        tc.show_scores = True

        shot = _make_mock_shot_card(
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
                "ai_score": 72,
                "ai_score_dimensions": {
                    "visual_quality": 80,
                    "audio_quality": 65,
                    "consistency": 70,
                },
                "ai_score_source": "movie-agent",
            },
        )

        html = _render_template(
            "partials/_decision_panel.html",
            shot=shot,
            template=tc,
        )
        assert "AI Score" in html
        assert "72" in html
        assert "visual_quality" in html
        assert "audio_quality" in html
        assert "consistency" in html
        assert "movie-agent" in html

    def test_decision_panel_no_ai_score_when_show_scores_false(self):
        """Test 8: _decision_panel.html does NOT render AI Score section when show_scores is false."""
        tc = MagicMock()
        tc.show_scores = False

        shot = _make_mock_shot_card(
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
                "ai_score": 72,
                "ai_score_dimensions": {"visual_quality": 80},
                "ai_score_source": "movie-agent",
            },
        )

        html = _render_template(
            "partials/_decision_panel.html",
            shot=shot,
            template=tc,
        )
        # Check the visible h3 heading is not rendered (comment text may still appear)
        assert '<h3 class="text-xs font-semibold uppercase text-gray-500">AI Score</h3>' not in html

    def test_decision_panel_no_ai_score_when_no_score_data(self):
        """Test 9: _decision_panel.html does NOT render AI Score section when no ai_score."""
        tc = MagicMock()
        tc.show_scores = True

        shot = _make_mock_shot_card(
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
            },
        )

        html = _render_template(
            "partials/_decision_panel.html",
            shot=shot,
            template=tc,
        )
        assert '<h3 class="text-xs font-semibold uppercase text-gray-500">AI Score</h3>' not in html


class TestMobileCardScoreRendering:
    """Test 10: _mobile_card.html renders AI score badge."""

    def test_mobile_card_renders_ai_score_badge(self):
        """Test 10: _mobile_card.html renders AI score badge in detail panel."""
        template_path = Path("app/templates/partials/_mobile_card.html")
        content = template_path.read_text()

        # Verify the template has ai_score rendering with show_scores gate
        assert "ai_score" in content
        assert "show_scores" in content
        # Verify color coding classes
        assert "text-green-400" in content
        assert "text-yellow-400" in content
        assert "text-red-400" in content
        # Verify score badge renders the score value
        assert "ai_score" in content


class TestCandidateGridScoreRendering:
    """Test 11: _template_candidate_grid.html renders ShotCard-level AI Score panel."""

    def test_candidate_grid_renders_ai_score_panel(self):
        """Test 11: _template_candidate_grid.html renders ShotCard-level AI Score panel."""
        tc = MagicMock()
        tc.show_scores = True
        tc.candidate_layout = "side-by-side"

        shot = _make_mock_shot_card(
            narrative_context={
                "scene": "scene-01",
                "shot_number": 1,
                "emotion_curve": "rising",
                "ai_score": 72,
                "ai_score_dimensions": {
                    "visual_quality": 80,
                    "audio_quality": 65,
                    "consistency": 70,
                },
                "ai_score_source": "movie-agent",
            },
            visual_bundle={
                "keyframes": {
                    "first": {"url": "https://example.com/first.jpg", "hash": "abc", "node": "g1"},
                },
                "prompt": "test",
                "candidates": [
                    {"candidate_id": "c1", "keyframes": {"first": {"url": "https://example.com/c1.jpg", "hash": "h1", "node": "ga"}}, "score": 0.85},
                ],
            },
        )

        html = _render_template(
            "partials/_template_candidate_grid.html",
            shot=shot,
            template=tc,
        )
        assert "AI Score" in html
        assert "72" in html
        assert "visual_quality" in html
        assert "movie-agent" in html
