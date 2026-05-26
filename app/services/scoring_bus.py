"""Scoring plugin bus for AI audit Phase 0.

Provides ScoringPlugin ABC, NullScoringPlugin (returns empty vectors),
ScoreVector data model, and ScoringBus orchestrator.

Phase 0: all dimensions are None. Future phases will plug in real models.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ScoreVector(BaseModel):
    """5-dimensional scoring output for a Shot Card.

    All dimensions default to None (Phase 0). Future phases will
    populate with float scores from AI models.
    """

    aesthetics: float | None = None
    consistency: float | None = None
    compliance: float | None = None
    technical_quality: float | None = None
    audio_match: float | None = None
    plugin_name: str = ""
    plugin_version: str = ""


class ScoringPlugin(ABC):
    """Abstract base class for scoring plugins.

    Each plugin scores a Shot Card and returns a ScoreVector.
    Plugins are registered with ScoringBus which orchestrates
    scoring across all registered plugins.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string."""
        ...

    @abstractmethod
    async def score(self, shot_card: Any) -> ScoreVector:
        """Score a Shot Card and return a ScoreVector.

        Args:
            shot_card: ShotCard ORM object or None (Phase 0 tolerant).

        Returns:
            ScoreVector with scoring dimensions populated.
        """
        ...


class NullScoringPlugin(ScoringPlugin):
    """Phase 0 placeholder scorer returning empty ScoreVector.

    All dimensions are None. Used as the default scorer until
    real AI models are registered in future phases.
    """

    @property
    def name(self) -> str:
        return "null_scorer"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def score(self, shot_card: Any) -> ScoreVector:
        return ScoreVector(
            aesthetics=None,
            consistency=None,
            compliance=None,
            technical_quality=None,
            audio_match=None,
            plugin_name="null_scorer",
            plugin_version="0.1.0",
        )


class ScoringBus:
    """Orchestrates scoring across registered plugins.

    Iterates all plugins and collects their ScoreVectors for a given
    Shot Card input. In Phase 0, only NullScoringPlugin is registered.
    """

    def __init__(self, plugins: list[ScoringPlugin] | None = None):
        self._plugins: list[ScoringPlugin] = plugins or []

    async def score(self, shot_card: Any) -> list[ScoreVector]:
        """Run all registered plugins and return list of ScoreVectors."""
        results: list[ScoreVector] = []
        for plugin in self._plugins:
            sv = await plugin.score(shot_card)
            results.append(sv)
        return results


# Module-level singleton
_scoring_bus: ScoringBus | None = None


def get_scoring_bus() -> ScoringBus:
    """Return singleton ScoringBus with NullScoringPlugin registered."""
    global _scoring_bus
    if _scoring_bus is None:
        _scoring_bus = ScoringBus(plugins=[NullScoringPlugin()])
    return _scoring_bus
