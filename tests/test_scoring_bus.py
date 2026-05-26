"""Tests for scoring bus: ScoringPlugin ABC, NullScoringPlugin, ScoreVector, ScoringBus."""

import pytest

from app.services.scoring_bus import (
    NullScoringPlugin,
    ScoreVector,
    ScoringBus,
    ScoringPlugin,
    get_scoring_bus,
)


# ---------------------------------------------------------------------------
# ScoreVector
# ---------------------------------------------------------------------------


class TestScoreVector:
    def test_default_dimensions_are_none(self):
        sv = ScoreVector()
        assert sv.aesthetics is None
        assert sv.consistency is None
        assert sv.compliance is None
        assert sv.technical_quality is None
        assert sv.audio_match is None

    def test_plugin_name_and_version_defaults(self):
        sv = ScoreVector()
        assert sv.plugin_name == ""
        assert sv.plugin_version == ""

    def test_all_five_dimensions_set(self):
        sv = ScoreVector(
            aesthetics=0.9,
            consistency=0.8,
            compliance=1.0,
            technical_quality=0.7,
            audio_match=0.6,
            plugin_name="test",
            plugin_version="1.0",
        )
        assert sv.aesthetics == 0.9
        assert sv.consistency == 0.8
        assert sv.compliance == 1.0
        assert sv.technical_quality == 0.7
        assert sv.audio_match == 0.6


# ---------------------------------------------------------------------------
# NullScoringPlugin
# ---------------------------------------------------------------------------


class TestNullScoringPlugin:
    def test_name(self):
        plugin = NullScoringPlugin()
        assert plugin.name == "null_scorer"

    def test_version(self):
        plugin = NullScoringPlugin()
        assert plugin.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_score_returns_all_none_dimensions(self):
        plugin = NullScoringPlugin()
        sv = await plugin.score(None)
        assert isinstance(sv, ScoreVector)
        assert sv.aesthetics is None
        assert sv.consistency is None
        assert sv.compliance is None
        assert sv.technical_quality is None
        assert sv.audio_match is None
        assert sv.plugin_name == "null_scorer"
        assert sv.plugin_version == "0.1.0"


# ---------------------------------------------------------------------------
# ScoringBus
# ---------------------------------------------------------------------------


class TestScoringBus:
    @pytest.mark.asyncio
    async def test_score_with_null_plugin_returns_one_vector(self):
        bus = ScoringBus(plugins=[NullScoringPlugin()])
        results = await bus.score(None)
        assert len(results) == 1
        assert results[0].plugin_name == "null_scorer"

    @pytest.mark.asyncio
    async def test_score_with_multiple_plugins(self):
        bus = ScoringBus(plugins=[NullScoringPlugin(), NullScoringPlugin()])
        results = await bus.score(None)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_score_with_no_plugins_returns_empty(self):
        bus = ScoringBus(plugins=[])
        results = await bus.score(None)
        assert results == []


# ---------------------------------------------------------------------------
# get_scoring_bus singleton
# ---------------------------------------------------------------------------


class TestGetScoringBus:
    def test_returns_scoring_bus_instance(self):
        bus = get_scoring_bus()
        assert isinstance(bus, ScoringBus)

    def test_singleton(self):
        bus1 = get_scoring_bus()
        bus2 = get_scoring_bus()
        assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_singleton_has_null_plugin(self):
        bus = get_scoring_bus()
        results = await bus.score(None)
        assert len(results) >= 1
        assert any(r.plugin_name == "null_scorer" for r in results)
