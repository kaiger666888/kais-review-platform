"""Tests for the Shot Card aggregation pipeline.

Tests cover: TopologyCollapser (all node types), ProgressiveFillEngine
(deep merge, min_audit_set, bundle completeness), and integration-level
aggregation pipeline with mocked database.
"""

import pytest

from app.services.topology_collapser import TopologyCollapser, NODE_BUNDLE_MAP
from app.services.progressive_fill import ProgressiveFillEngine


# ---------------------------------------------------------------------------
# TopologyCollapser tests
# ---------------------------------------------------------------------------


class TestTopologyCollapse:
    """Test DAG node output mapping to Shot Card bundle fields."""

    def setup_method(self):
        self.collapser = TopologyCollapser()

    def test_topology_collapse_visual(self):
        """FLUX.1-dev node collapses to visual_bundle.keyframes.first."""
        output = {"url": "https://example.com/first.png", "hash": "abc123"}
        result = self.collapser.collapse("FLUX.1-dev", output)

        assert result["target_column"] == "visual_bundle"
        assert result["merge_data"] == {
            "keyframes": {"first": {"url": "https://example.com/first.png", "hash": "abc123"}}
        }

    def test_topology_collapse_visual_last_frame(self):
        """img2img node collapses to visual_bundle.keyframes.last."""
        output = {"url": "https://example.com/last.png", "hash": "def456"}
        result = self.collapser.collapse("img2img", output)

        assert result["target_column"] == "visual_bundle"
        assert result["merge_data"] == {
            "keyframes": {"last": {"url": "https://example.com/last.png", "hash": "def456"}}
        }

    def test_topology_collapse_video(self):
        """Wan2.2-T2V node collapses to visual_bundle.video_clip."""
        output = {"url": "https://example.com/video.mp4", "duration": 5.0, "node": "Wan2.2-T2V"}
        result = self.collapser.collapse("Wan2.2-T2V", output)

        assert result["target_column"] == "visual_bundle"
        assert result["merge_data"] == {"video_clip": output}

    def test_topology_collapse_prompt(self):
        """PromptNode collapses to visual_bundle.prompt."""
        output = {"text": "A cat sitting on a windowsill"}
        result = self.collapser.collapse("PromptNode", output)

        assert result["target_column"] == "visual_bundle"
        # PromptNode maps to path "prompt" which wraps output as {"prompt": output}
        assert "prompt" in result["merge_data"]

    def test_topology_collapse_audio(self):
        """AudioPrompt node collapses to audio_bundle.bgm_prompt."""
        output = {"text": "Gentle piano melody"}
        result = self.collapser.collapse("AudioPrompt", output)

        assert result["target_column"] == "audio_bundle"
        assert result["merge_data"] == {"bgm_prompt": output}

    def test_topology_collapse_sfx(self):
        """SFXPrompt node collapses to audio_bundle.sfx_prompt."""
        output = {"text": "Door creaking sound"}
        result = self.collapser.collapse("SFXPrompt", output)

        assert result["target_column"] == "audio_bundle"
        assert result["merge_data"] == {"sfx_prompt": output}

    def test_topology_collapse_audio_gen(self):
        """AudioGen node overrides output to {status: ready}."""
        output = {"file_url": "https://example.com/audio.mp3", "duration": 30}
        result = self.collapser.collapse("AudioGen", output)

        assert result["target_column"] == "audio_bundle"
        # AudioGen always overrides to status="ready"
        assert result["merge_data"] == {"status": "ready"}

    def test_topology_collapse_orchestrator(self):
        """ShotOrchestrator merges full dict into narrative_context."""
        output = {
            "scene": "INT. LIVING ROOM - DAY",
            "shot_number": 3,
            "emotion_curve": "rising",
            "continuity_tags": ["daytime", "indoor"],
        }
        result = self.collapser.collapse("ShotOrchestrator", output)

        assert result["target_column"] == "narrative_context"
        assert result["merge_data"] == output

    def test_topology_collapse_unknown_node(self):
        """Unknown node_type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown node type"):
            self.collapser.collapse("NonExistentNode", {})

    def test_all_node_types_in_map(self):
        """Verify all expected node types are in NODE_BUNDLE_MAP."""
        expected_types = [
            "FLUX.1-dev", "FLUX.1-dev-t2i", "img2img", "Wan2.2-T2V",
            "PromptNode", "AudioPrompt", "SFXPrompt", "AudioGen",
            "ShotOrchestrator",
        ]
        for nt in expected_types:
            assert nt in NODE_BUNDLE_MAP, f"Missing node type: {nt}"


# ---------------------------------------------------------------------------
# ProgressiveFillEngine._deep_merge tests
# ---------------------------------------------------------------------------


class TestDeepMerge:
    """Test order-agnostic deep merge of JSONB data."""

    def setup_method(self):
        self.engine = ProgressiveFillEngine()

    def test_deep_merge_preserves_existing(self):
        """Merging preserves existing nested keys while adding new ones."""
        base = {"keyframes": {"first": "a"}}
        override = {"keyframes": {"last": "b"}, "prompt": "x"}

        result = self.engine._deep_merge(base, override)

        assert result == {"keyframes": {"first": "a", "last": "b"}, "prompt": "x"}

    def test_deep_merge_empty_base(self):
        """Merging into empty base works correctly."""
        base = {}
        override = {"video_clip": {"url": "test.mp4", "duration": 5}}

        result = self.engine._deep_merge(base, override)

        assert result == {"video_clip": {"url": "test.mp4", "duration": 5}}

    def test_deep_merge_overwrites_non_dict(self):
        """Non-dict values in override replace base values."""
        base = {"prompt": "old prompt"}
        override = {"prompt": "new prompt"}

        result = self.engine._deep_merge(base, override)

        assert result == {"prompt": "new prompt"}

    def test_deep_merge_nested_three_levels(self):
        """Deep merge works correctly at 3+ nesting levels."""
        base = {"a": {"b": {"c": 1}}}
        override = {"a": {"b": {"d": 2}}}

        result = self.engine._deep_merge(base, override)

        assert result == {"a": {"b": {"c": 1, "d": 2}}}

    def test_deep_merge_does_not_mutate_base(self):
        """Original base dict is not modified."""
        base = {"keyframes": {"first": "a"}}
        base_copy = {"keyframes": {"first": "a"}}
        override = {"keyframes": {"last": "b"}}

        self.engine._deep_merge(base, override)

        assert base == base_copy


# ---------------------------------------------------------------------------
# ProgressiveFillEngine: min_audit_set checks
# ---------------------------------------------------------------------------


class TestMinAuditSet:
    """Test min_audit_set readiness evaluation."""

    def setup_method(self):
        self.engine = ProgressiveFillEngine()

    def _make_shot_card(self, visual_bundle=None, audio_bundle=None, min_audit_set=None):
        """Create a mock ShotCard-like object for testing."""
        class MockShotCard:
            def __init__(self):
                self.visual_bundle = visual_bundle
                self.audio_bundle = audio_bundle
                self.min_audit_set = min_audit_set
        return MockShotCard()

    def test_min_audit_set_visual_only_default(self):
        """ShotCard with only visual_bundle having data returns True for default set."""
        card = self._make_shot_card(
            visual_bundle={"keyframes": {"first": {"url": "a.png"}}, "prompt": "test"},
        )
        assert self.engine.check_min_audit_set(card) is True

    def test_min_audit_set_incomplete(self):
        """ShotCard with visual_bundle=None returns False."""
        card = self._make_shot_card(visual_bundle=None)
        assert self.engine.check_min_audit_set(card) is False

    def test_min_audit_set_empty_bundle(self):
        """ShotCard with empty visual_bundle {} returns False."""
        card = self._make_shot_card(visual_bundle={})
        assert self.engine.check_min_audit_set(card) is False

    def test_min_audit_set_both_bundles(self):
        """ShotCard requiring both bundles -- satisfied only when both present."""
        card = self._make_shot_card(
            visual_bundle={"keyframes": {"first": "a"}},
            audio_bundle={"bgm_prompt": "piano"},
            min_audit_set=["visual_bundle", "audio_bundle"],
        )
        assert self.engine.check_min_audit_set(card) is True

    def test_min_audit_set_missing_one_of_two(self):
        """ShotCard requiring both bundles -- fails when one is missing."""
        card = self._make_shot_card(
            visual_bundle={"keyframes": {"first": "a"}},
            audio_bundle=None,
            min_audit_set=["visual_bundle", "audio_bundle"],
        )
        assert self.engine.check_min_audit_set(card) is False

    def test_min_audit_set_null_min_audit_set(self):
        """When min_audit_set is None, defaults to visual_bundle."""
        card = self._make_shot_card(
            visual_bundle={"keyframes": {"first": "a"}},
            min_audit_set=None,
        )
        assert self.engine.check_min_audit_set(card) is True


# ---------------------------------------------------------------------------
# ProgressiveFillEngine: bundle completeness checks
# ---------------------------------------------------------------------------


class TestBundleComplete:
    """Test bundle completeness evaluation."""

    def setup_method(self):
        self.engine = ProgressiveFillEngine()

    def _make_shot_card(self, visual_bundle=None, audio_bundle=None):
        """Create a mock ShotCard-like object for testing."""
        class MockShotCard:
            def __init__(self):
                self.visual_bundle = visual_bundle
                self.audio_bundle = audio_bundle
        return MockShotCard()

    def test_bundle_complete_visual(self):
        """Visual bundle complete with keyframes.first and prompt."""
        card = self._make_shot_card(
            visual_bundle={
                "keyframes": {"first": {"url": "a.png", "hash": "abc"}},
                "prompt": "A scenic view",
            },
        )
        assert self.engine.check_bundle_complete(card, "visual_bundle") is True

    def test_bundle_complete_visual_no_prompt(self):
        """Visual bundle incomplete: has keyframes but no prompt."""
        card = self._make_shot_card(
            visual_bundle={"keyframes": {"first": {"url": "a.png"}}},
        )
        assert self.engine.check_bundle_complete(card, "visual_bundle") is False

    def test_bundle_complete_visual_no_keyframes_first(self):
        """Visual bundle incomplete: has keyframes but no first frame."""
        card = self._make_shot_card(
            visual_bundle={"keyframes": {"last": {"url": "b.png"}}, "prompt": "test"},
        )
        assert self.engine.check_bundle_complete(card, "visual_bundle") is False

    def test_bundle_complete_visual_none(self):
        """Visual bundle None returns False."""
        card = self._make_shot_card(visual_bundle=None)
        assert self.engine.check_bundle_complete(card, "visual_bundle") is False

    def test_bundle_complete_audio(self):
        """Audio bundle complete with bgm_prompt and status=ready."""
        card = self._make_shot_card(
            audio_bundle={"bgm_prompt": "piano melody", "status": "ready"},
        )
        assert self.engine.check_bundle_complete(card, "audio_bundle") is True

    def test_bundle_complete_audio_sfx(self):
        """Audio bundle complete with sfx_prompt and status=ready."""
        card = self._make_shot_card(
            audio_bundle={"sfx_prompt": "door creak", "status": "ready"},
        )
        assert self.engine.check_bundle_complete(card, "audio_bundle") is True

    def test_bundle_complete_audio_pending(self):
        """Audio bundle incomplete: status still pending."""
        card = self._make_shot_card(
            audio_bundle={"bgm_prompt": "piano melody", "status": "pending"},
        )
        assert self.engine.check_bundle_complete(card, "audio_bundle") is False

    def test_bundle_complete_audio_no_prompts(self):
        """Audio bundle incomplete: no bgm_prompt or sfx_prompt."""
        card = self._make_shot_card(
            audio_bundle={"status": "ready"},
        )
        assert self.engine.check_bundle_complete(card, "audio_bundle") is False

    def test_bundle_complete_audio_none(self):
        """Audio bundle None returns False."""
        card = self._make_shot_card(audio_bundle=None)
        assert self.engine.check_bundle_complete(card, "audio_bundle") is False

    def test_bundle_complete_unknown_bundle(self):
        """Unknown bundle name: non-empty dict is sufficient."""
        card = self._make_shot_card()
        card.custom_bundle = {"data": "value"}
        assert self.engine.check_bundle_complete(card, "custom_bundle") is True


# ---------------------------------------------------------------------------
# Out-of-order processing tests
# ---------------------------------------------------------------------------


class TestOutOfOrderProcessing:
    """Test that nodes arriving out of order produce correct results."""

    def setup_method(self):
        self.collapser = TopologyCollapser()
        self.engine = ProgressiveFillEngine()

    def test_out_of_order_video_before_keyframes(self):
        """Video arriving before keyframes: both merge correctly into visual_bundle."""
        # Video arrives first
        video_output = {"url": "video.mp4", "duration": 5.0, "node": "Wan2.2-T2V"}
        video_result = self.collapser.collapse("Wan2.2-T2V", video_output)
        assert video_result["target_column"] == "visual_bundle"
        assert video_result["merge_data"] == {"video_clip": video_output}

        # Keyframes arrive second
        flux_output = {"url": "first.png", "hash": "abc"}
        flux_result = self.collapser.collapse("FLUX.1-dev", flux_output)
        assert flux_result["target_column"] == "visual_bundle"
        assert flux_result["merge_data"] == {
            "keyframes": {"first": {"url": "first.png", "hash": "abc"}}
        }

        # Deep merge should combine both without conflict
        merged = self.engine._deep_merge(
            video_result["merge_data"],
            flux_result["merge_data"],
        )
        assert "video_clip" in merged
        assert "keyframes" in merged
        assert merged["keyframes"]["first"]["url"] == "first.png"
        assert merged["video_clip"]["duration"] == 5.0

    def test_out_of_order_audio_before_visual(self):
        """Audio arriving before visual: both bundles fill independently."""
        audio_output = {"text": "Gentle piano"}
        audio_result = self.collapser.collapse("AudioPrompt", audio_output)
        assert audio_result["target_column"] == "audio_bundle"

        visual_output = {"url": "frame.png", "hash": "xyz"}
        visual_result = self.collapser.collapse("FLUX.1-dev", visual_output)
        assert visual_result["target_column"] == "visual_bundle"

        # Different target columns -- no conflict
        assert audio_result["target_column"] != visual_result["target_column"]

    def test_out_of_order_last_then_first_keyframe(self):
        """Last frame arriving before first frame: deep merge preserves both."""
        last_output = {"url": "last.png", "hash": "def"}
        last_result = self.collapser.collapse("img2img", last_output)
        assert last_result["merge_data"] == {
            "keyframes": {"last": {"url": "last.png", "hash": "def"}}
        }

        first_output = {"url": "first.png", "hash": "abc"}
        first_result = self.collapser.collapse("FLUX.1-dev", first_output)
        assert first_result["merge_data"] == {
            "keyframes": {"first": {"url": "first.png", "hash": "abc"}}
        }

        # Deep merge preserves both keyframes
        merged = self.engine._deep_merge(
            last_result["merge_data"],
            first_result["merge_data"],
        )
        assert merged == {
            "keyframes": {
                "first": {"url": "first.png", "hash": "abc"},
                "last": {"url": "last.png", "hash": "def"},
            }
        }


# ---------------------------------------------------------------------------
# Aggregator integration test (with mocked DB)
# ---------------------------------------------------------------------------


class TestAggregatorPipeline:
    """Test the full aggregation pipeline with mocked database."""

    @pytest.mark.asyncio
    async def test_aggregator_full_pipeline_visual_only(self):
        """FLUX event creates Shot Card and fills visual bundle."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services.aggregator import ShotCardAggregator

        # Create mock shot card
        mock_shot_card = MagicMock()
        mock_shot_card.id = 1
        mock_shot_card.shot_id = "shot-001"
        mock_shot_card.project_id = "proj-001"
        mock_shot_card.audit_status = "awaiting_audit"
        mock_shot_card.visual_bundle = {
            "keyframes": {"first": {"url": "frame.png", "hash": "abc"}},
        }
        mock_shot_card.audio_bundle = None
        mock_shot_card.min_audit_set = ["visual_bundle"]

        aggregator = ShotCardAggregator()

        # Mock _ensure_shot_card to return our mock
        aggregator._ensure_shot_card = AsyncMock(return_value=mock_shot_card)

        # Mock filler.fill to return updated card with visual data
        mock_shot_card_filled = MagicMock()
        mock_shot_card_filled.id = 1
        mock_shot_card_filled.shot_id = "shot-001"
        mock_shot_card_filled.project_id = "proj-001"
        mock_shot_card_filled.audit_status = "awaiting_audit"
        mock_shot_card_filled.visual_bundle = {
            "keyframes": {"first": {"url": "frame.png", "hash": "abc"}},
        }
        mock_shot_card_filled.audio_bundle = None
        mock_shot_card_filled.min_audit_set = ["visual_bundle"]

        aggregator.filler.fill = AsyncMock(return_value=mock_shot_card_filled)
        aggregator.filler.check_min_audit_set = MagicMock(return_value=True)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=False)
        aggregator._emit_events = AsyncMock()

        event = {
            "execution_id": "exec-001",
            "shot_id": "shot-001",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png", "hash": "abc"},
        }

        result = await aggregator.handle_node_completion(event)

        assert result["status"] == "ok"
        assert result["shot_id"] == "shot-001"
        assert result["updated_column"] == "visual_bundle"
        assert result["bundle_complete"] is False
        assert result["min_audit_satisfied"] is True

    @pytest.mark.asyncio
    async def test_aggregator_full_pipeline_with_audio(self):
        """FLUX + AudioPrompt events produce correctly assembled Shot Card."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()

        # Mock shot card with both visual and audio data
        mock_shot_card = MagicMock()
        mock_shot_card.id = 1
        mock_shot_card.shot_id = "shot-002"
        mock_shot_card.project_id = "proj-001"
        mock_shot_card.audit_status = "awaiting_audit"
        mock_shot_card.visual_bundle = {
            "keyframes": {"first": {"url": "frame.png"}},
            "prompt": "scenic view",
        }
        mock_shot_card.audio_bundle = {"bgm_prompt": "piano melody", "status": "ready"}
        mock_shot_card.min_audit_set = ["visual_bundle"]

        aggregator._ensure_shot_card = AsyncMock(return_value=mock_shot_card)
        aggregator.filler.fill = AsyncMock(return_value=mock_shot_card)
        aggregator.filler.check_min_audit_set = MagicMock(return_value=True)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=True)
        aggregator._emit_events = AsyncMock()

        event = {
            "execution_id": "exec-002",
            "shot_id": "shot-002",
            "project_id": "proj-001",
            "node_type": "AudioPrompt",
            "node_output": {"text": "piano melody"},
        }

        result = await aggregator.handle_node_completion(event)

        assert result["status"] == "ok"
        assert result["shot_id"] == "shot-002"
        assert result["updated_column"] == "audio_bundle"
        assert result["bundle_complete"] is True
        assert result["min_audit_satisfied"] is True

    @pytest.mark.asyncio
    async def test_aggregator_failed_shot_card_creation(self):
        """Aggregator returns error when Shot Card creation fails."""
        from unittest.mock import AsyncMock

        from app.services.aggregator import ShotCardAggregator

        aggregator = ShotCardAggregator()
        aggregator._ensure_shot_card = AsyncMock(return_value=None)

        event = {
            "execution_id": "exec-003",
            "shot_id": "shot-003",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png"},
        }

        result = await aggregator.handle_node_completion(event)

        assert result["status"] == "error"
        assert result["reason"] == "failed_to_create_shot_card"

    @pytest.mark.asyncio
    async def test_aggregator_emits_bundle_ready_event(self):
        """Aggregator emits bundle_ready when bundle is complete."""
        from unittest.mock import AsyncMock, MagicMock, call

        from app.services.aggregator import ShotCardAggregator

        mock_shot_card = MagicMock()
        mock_shot_card.id = 1
        mock_shot_card.shot_id = "shot-004"
        mock_shot_card.project_id = "proj-001"
        mock_shot_card.audit_status = "awaiting_audit"

        aggregator = ShotCardAggregator()
        aggregator._ensure_shot_card = AsyncMock(return_value=mock_shot_card)
        aggregator.filler.fill = AsyncMock(return_value=mock_shot_card)
        aggregator.filler.check_min_audit_set = MagicMock(return_value=True)
        aggregator.filler.check_bundle_complete = MagicMock(return_value=True)
        aggregator._emit_events = AsyncMock()

        event = {
            "execution_id": "exec-004",
            "shot_id": "shot-004",
            "project_id": "proj-001",
            "node_type": "FLUX.1-dev",
            "node_output": {"url": "frame.png", "hash": "abc"},
        }

        await aggregator.handle_node_completion(event)

        # Verify _emit_events was called with bundle_complete=True
        aggregator._emit_events.assert_called_once_with(
            shot_card=mock_shot_card,
            target_column="visual_bundle",
            bundle_complete=True,
            min_audit_satisfied=True,
        )
