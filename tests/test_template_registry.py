"""Unit tests for TemplateRegistry: YAML loading, validation, resolution, fallback."""

import textwrap

import pytest

from app.core.template_registry import (
    TemplateConfig,
    TemplateRegistry,
    TemplateValidationError,
    derive_source_system,
    get_template_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_yaml(**overrides) -> str:
    """Build a minimal valid template YAML string."""
    base = {
        "name": "test-template",
        "version": "1.0",
        "source_system": "test-system",
        "templates": {
            "_default": {
                "desktop": {
                    "decision_panel": "partials/_decision_panel.html",
                    "media_player": "partials/_media_player.html",
                },
                "mobile": {
                    "card_variant": "default",
                },
            },
        },
    }
    base.update(overrides)
    import yaml
    return yaml.dump(base, default_flow_style=False)


# ---------------------------------------------------------------------------
# Test 1: load_from_directory loads all YAML files and indexes by source_system
# ---------------------------------------------------------------------------


class TestLoadFromDirectory:
    def test_loads_all_yaml_and_indexes_by_source_system(self, tmp_path):
        """load_from_directory should load all *.yaml files, index by source_system."""
        # Write two YAML files
        (tmp_path / "alpha.yaml").write_text(
            _make_yaml(name="alpha", source_system="alpha-system")
        )
        (tmp_path / "beta.yaml").write_text(
            _make_yaml(name="beta", source_system="beta-system")
        )
        # Non-YAML file should be ignored
        (tmp_path / "readme.md").write_text("not yaml")

        registry = TemplateRegistry()
        loaded = registry.load_from_directory(str(tmp_path))

        assert sorted(loaded) == ["alpha", "beta"]
        assert sorted(registry.list_templates()) == ["alpha-system", "beta-system"]

    def test_empty_directory_returns_empty(self, tmp_path):
        registry = TemplateRegistry()
        loaded = registry.load_from_directory(str(tmp_path))
        assert loaded == []


# ---------------------------------------------------------------------------
# Test 2: resolve("kais-movie-agent", "art-direction") returns TemplateConfig
#          with show_scores=True, show_candidates=True, candidate_layout="side-by-side"
# ---------------------------------------------------------------------------


class TestResolveMovieAgent:
    def test_art_direction_template(self, tmp_path):
        yaml_content = textwrap.dedent("""\
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
                mobile:
                  card_variant: default
        """)
        (tmp_path / "movie-agent.yaml").write_text(yaml_content)

        registry = TemplateRegistry()
        registry.load_from_directory(str(tmp_path))

        config = registry.resolve("kais-movie-agent", "art-direction")
        assert isinstance(config, TemplateConfig)
        assert config.show_scores is True
        assert config.show_candidates is True
        assert config.candidate_layout == "side-by-side"


# ---------------------------------------------------------------------------
# Test 3: resolve("kais-gold-team", "task-parameter") returns show_scores=False
# ---------------------------------------------------------------------------


class TestResolveGoldTeam:
    def test_task_parameter_template(self, tmp_path):
        yaml_content = textwrap.dedent("""\
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
        """)
        (tmp_path / "gold-team.yaml").write_text(yaml_content)

        registry = TemplateRegistry()
        registry.load_from_directory(str(tmp_path))

        config = registry.resolve("kais-gold-team", "task-parameter")
        assert config.show_scores is False
        assert config.show_candidates is False
        assert config.desktop_decision_panel == "partials/_template_risk_assessment.html"


# ---------------------------------------------------------------------------
# Test 4: resolve("unknown-system", "unknown-phase") returns default TemplateConfig
# ---------------------------------------------------------------------------


class TestResolveFallbackGlobal:
    def test_unknown_system_returns_default(self):
        registry = TemplateRegistry()
        config = registry.resolve("unknown-system", "unknown-phase")
        assert isinstance(config, TemplateConfig)
        # Should have all default values
        assert config.show_scores is False
        assert config.show_candidates is True
        assert config.candidate_layout == "grid"
        assert config.desktop_decision_panel == "partials/_decision_panel.html"


# ---------------------------------------------------------------------------
# Test 5: resolve("kais-movie-agent", "nonexistent-phase") falls back to
#          _default within source_system
# ---------------------------------------------------------------------------


class TestResolveFallbackWithinSource:
    def test_nonexistent_phase_falls_back_to_source_default(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            name: movie-agent-templates
            version: "1.0"
            source_system: kais-movie-agent
            templates:
              art-direction:
                desktop:
                  decision_panel: partials/_template_candidate_grid.html
                  show_scores: true
              _default:
                desktop:
                  decision_panel: partials/_decision_panel.html
                  media_player: partials/_media_player.html
                  show_scores: false
                  show_candidates: false
        """)
        (tmp_path / "movie-agent.yaml").write_text(yaml_content)

        registry = TemplateRegistry()
        registry.load_from_directory(str(tmp_path))

        config = registry.resolve("kais-movie-agent", "nonexistent-phase")
        assert config.show_scores is False
        assert config.show_candidates is False
        assert config.desktop_decision_panel == "partials/_decision_panel.html"


# ---------------------------------------------------------------------------
# Test 6: Invalid YAML (missing required fields) raises TemplateValidationError
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_missing_required_fields_raises_error(self, tmp_path):
        """YAML missing required 'source_system' should raise TemplateValidationError."""
        import yaml
        bad_yaml = yaml.dump({
            "name": "broken",
            "version": "1.0",
            # missing source_system and templates
        })
        (tmp_path / "bad.yaml").write_text(bad_yaml)

        registry = TemplateRegistry()
        with pytest.raises(TemplateValidationError):
            registry.load_from_directory(str(tmp_path))

    def test_invalid_yaml_syntax_raises_error(self):
        """Non-parseable YAML should raise TemplateValidationError."""
        registry = TemplateRegistry()
        with pytest.raises(TemplateValidationError):
            registry.validate_template(":\n  - bad: [yaml: content")


# ---------------------------------------------------------------------------
# Test 7: YAML with non-partials/ include path raises TemplateValidationError
# ---------------------------------------------------------------------------


class TestPathSecurity:
    def test_non_partials_path_raises_error(self, tmp_path):
        """Include paths not starting with 'partials/' should be rejected."""
        yaml_content = textwrap.dedent("""\
            name: evil-template
            version: "1.0"
            source_system: evil-system
            templates:
              _default:
                desktop:
                  decision_panel: ../etc/passwd
                  media_player: partials/_media_player.html
        """)
        (tmp_path / "evil.yaml").write_text(yaml_content)

        registry = TemplateRegistry()
        with pytest.raises(TemplateValidationError, match="partials/"):
            registry.load_from_directory(str(tmp_path))

    def test_partials_path_passes(self, tmp_path):
        """Valid partials/ path should load without error."""
        yaml_content = textwrap.dedent("""\
            name: safe-template
            version: "1.0"
            source_system: safe-system
            templates:
              _default:
                desktop:
                  decision_panel: partials/_decision_panel.html
                  media_player: partials/_media_player.html
        """)
        (tmp_path / "safe.yaml").write_text(yaml_content)

        registry = TemplateRegistry()
        loaded = registry.load_from_directory(str(tmp_path))
        assert "safe-template" in loaded


# ---------------------------------------------------------------------------
# Test 8-11: derive_source_system
# ---------------------------------------------------------------------------


class MockShotCard:
    """Minimal mock for ShotCard with narrative_context and project_id."""

    def __init__(self, narrative_context=None, project_id=""):
        self.narrative_context = narrative_context or {}
        self.project_id = project_id


class TestDeriveSourceSystem:
    def test_from_narrative_context_source_system(self):
        """Test 8: derive from narrative_context.source_system first."""
        card = MockShotCard(
            narrative_context={"source_system": "kais-movie-agent"},
            project_id="gold-team-project-001",
        )
        assert derive_source_system(card) == "kais-movie-agent"

    def test_from_project_id_movie_agent_prefix(self):
        """Test 9: project_id starting 'movie-agent' -> 'kais-movie-agent'."""
        card = MockShotCard(
            narrative_context={},
            project_id="movie-agent-project-001",
        )
        assert derive_source_system(card) == "kais-movie-agent"

    def test_from_project_id_gold_team_prefix(self):
        """Test 10: project_id starting 'gold-team' -> 'kais-gold-team'."""
        card = MockShotCard(
            narrative_context={},
            project_id="gold-team-render-0042",
        )
        assert derive_source_system(card) == "kais-gold-team"

    def test_no_match_returns_unknown(self):
        """Test 11: no match returns 'unknown'."""
        card = MockShotCard(
            narrative_context={},
            project_id="unknown-project-999",
        )
        assert derive_source_system(card) == "unknown"

    def test_empty_narrative_context_uses_project_id(self):
        """narrative_context with empty source_system falls back to project_id."""
        card = MockShotCard(
            narrative_context={"source_system": ""},
            project_id="movie-agent-001",
        )
        assert derive_source_system(card) == "kais-movie-agent"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestGetTemplateRegistry:
    def test_returns_template_registry_instance(self):
        registry = get_template_registry()
        assert isinstance(registry, TemplateRegistry)
