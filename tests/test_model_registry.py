"""Tests for model registry: ModelInfo, ModelRegistry, get_model_registry."""

from app.services.model_registry import ModelInfo, ModelRegistry, get_model_registry


class TestModelInfo:
    def test_fields(self):
        info = ModelInfo(name="test_model", version="1.0", status="model_unavailable")
        assert info.name == "test_model"
        assert info.version == "1.0"
        assert info.status == "model_unavailable"


class TestModelRegistry:
    def test_get_model_returns_unavailable(self):
        registry = ModelRegistry()
        info = registry.get_model("any_name")
        assert info.name == "any_name"
        assert info.version == "0.0.0"
        assert info.status == "model_unavailable"

    def test_get_model_unknown_name_returns_unavailable(self):
        registry = ModelRegistry()
        info = registry.get_model("nonexistent_model_v42")
        assert info.status == "model_unavailable"

    def test_list_models_returns_empty(self):
        registry = ModelRegistry()
        models = registry.list_models()
        assert models == []


class TestGetModelRegistry:
    def test_returns_model_registry_instance(self):
        registry = get_model_registry()
        assert isinstance(registry, ModelRegistry)

    def test_singleton(self):
        r1 = get_model_registry()
        r2 = get_model_registry()
        assert r1 is r2
