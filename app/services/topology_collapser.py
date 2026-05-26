"""Topology Collapser -- maps OpenClaw DAG node outputs to Shot Card bundle fields.

Maps each node type (FLUX.1-dev, Wan2.2-T2V, AudioPrompt, etc.) to the
correct Shot Card JSONB column and path within that column. Order-agnostic:
handles video arriving before keyframes, audio before visual, etc.
"""

# Registry: node_type -> (target_bundle, target_path_within_bundle)
NODE_BUNDLE_MAP: dict[str, tuple[str, str | None]] = {
    # Visual bundle nodes
    "FLUX.1-dev": ("visual_bundle", "keyframes.first"),  # Text-to-image first frame
    "FLUX.1-dev-t2i": ("visual_bundle", "keyframes.first"),
    "img2img": ("visual_bundle", "keyframes.last"),  # Image-to-image last frame
    "Wan2.2-T2V": ("visual_bundle", "video_clip"),  # Text-to-video
    "PromptNode": ("visual_bundle", "prompt"),  # Visual prompt
    # Audio bundle nodes
    "AudioPrompt": ("audio_bundle", "bgm_prompt"),
    "SFXPrompt": ("audio_bundle", "sfx_prompt"),
    "AudioGen": ("audio_bundle", "status"),  # Sets status to "ready"
    # Narrative context (from first/orchestrator node)
    "ShotOrchestrator": ("narrative_context", None),  # Full dict merge
}


class TopologyCollapser:
    """Collapses DAG node outputs into Shot Card bundle structures.

    Order-agnostic: handles video arriving before keyframes,
    audio arriving before visual, etc.
    """

    def collapse(self, node_type: str, node_output: dict) -> dict:
        """Map a single node output to a Shot Card field update.

        Args:
            node_type: OpenClaw node type string (e.g. "FLUX.1-dev").
            node_output: The output data from the completed node.

        Returns:
            Dict with:
                target_column: "visual_bundle" | "audio_bundle" | "narrative_context"
                merge_data: dict to merge into the target column

        Raises:
            ValueError: If node_type is not in NODE_BUNDLE_MAP.
        """
        mapping = NODE_BUNDLE_MAP.get(node_type)
        if mapping is None:
            raise ValueError(f"Unknown node type: {node_type}")

        target_column, path = mapping

        # Narrative context is a full dict merge, no path nesting needed
        if target_column == "narrative_context":
            return {"target_column": target_column, "merge_data": node_output}

        # AudioGen node overrides output -- sets status to "ready"
        if node_type == "AudioGen":
            return {
                "target_column": target_column,
                "merge_data": {"status": "ready"},
            }

        # Build the nested dict structure for this node's contribution
        if target_column == "visual_bundle":
            merge_data = self._build_visual_merge(path, node_output)
        elif target_column == "audio_bundle":
            merge_data = self._build_audio_merge(path, node_output)
        else:
            raise ValueError(f"Unknown target column: {target_column}")

        return {"target_column": target_column, "merge_data": merge_data}

    def _build_visual_merge(self, path: str, output: dict) -> dict:
        """Build nested dict for visual_bundle path.

        Examples:
            path="keyframes.first" -> {"keyframes": {"first": output}}
            path="video_clip" -> {"video_clip": output}
        """
        parts = path.split(".")
        result = output
        for part in reversed(parts):
            result = {part: result}
        return result

    def _build_audio_merge(self, path: str, output: dict) -> dict:
        """Build nested dict for audio_bundle path.

        Examples:
            path="bgm_prompt" -> {"bgm_prompt": output}
            path="status" -> {"status": output}
        """
        parts = path.split(".")
        result = output
        for part in reversed(parts):
            result = {part: result}
        return result
