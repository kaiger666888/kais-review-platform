"""Model registry for AI audit model discovery.

Phase 0: all model queries return model_unavailable.
Future phases will register real AI models.
"""

from typing import Literal

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Metadata for a registered AI model."""

    name: str
    version: str
    status: Literal["available", "model_unavailable"]


class ModelRegistry:
    """Registry of available AI models.

    Phase 0: no models registered. All queries return model_unavailable.
    Future phases will register models loaded from configuration.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}

    def get_model(self, name: str) -> ModelInfo:
        """Look up a model by name.

        Phase 0 always returns model_unavailable.
        """
        if name in self._models:
            return self._models[name]
        return ModelInfo(name=name, version="0.0.0", status="model_unavailable")

    def list_models(self) -> list[ModelInfo]:
        """List all registered models.

        Phase 0 returns empty list.
        """
        return list(self._models.values())


# Module-level singleton
_model_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Return singleton ModelRegistry."""
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry
