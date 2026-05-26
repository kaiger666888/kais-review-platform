"""Tests for GitPolicyProvider: Git repo management, SHA-based caching,
project-specific policies, commit-specific reads, and local fallback."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from app.services.git_policy_provider import GitPolicyProvider, get_git_policy_provider


# ---------------------------------------------------------------------------
# Sample YAML policies for test fixtures
# ---------------------------------------------------------------------------

GLOBAL_ROUTING_YAML = """\
name: global_routing
version: "1.0"
rules:
  - name: auto_low_risk
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.emotion_curve
          operator: equals
          value: neutral
    disposition: AUTO
"""

PROJECT_STRICT_YAML = """\
name: project_strict
version: "1.0"
rules:
  - name: block_flagged
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: narrative_context.continuity_tags
          operator: contains
          value: flagged
    disposition: BLOCK
"""

TEMP_OVERRIDE_YAML = """\
name: temp_override
version: "1.0"
rules:
  - name: human_all
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: project_id
          operator: equals
          value: proj-001
    disposition: HUMAN
"""


# ---------------------------------------------------------------------------
# Helpers for mocking git.Repo tree structures
# ---------------------------------------------------------------------------


class MockBlob:
    """Simulates a GitPython blob with data_stream.read().decode()."""

    def __init__(self, content: str):
        self._content = content.encode("utf-8")

    @property
    def data_stream(self):
        stream = MagicMock()
        stream.read.return_value = self._content
        return stream


class MockTree(dict):
    """Simulates a GitPython tree (dict-like path access)."""

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            raise KeyError(f"No such file or directory: '{key}'")


def _make_mock_tree(policies: dict[str, dict[str, str]]) -> MockTree:
    """Build a mock tree from {layer_name: {filename: yaml_content}}.

    Creates: tree["policies"][layer_name][filename] -> MockBlob
    """
    layers: dict[str, MockTree] = {}
    for layer_name, files in policies.items():
        blobs = {fname: MockBlob(content) for fname, content in files.items()}
        layers[layer_name] = MockTree(blobs)

    policies_tree = MockTree(layers)
    return MockTree({"policies": policies_tree})


def _make_mock_repo(head_sha: str, tree: MockTree) -> MagicMock:
    """Create a mock git.Repo with a specific HEAD SHA and tree."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = head_sha
    mock_repo.head.commit.tree = tree
    mock_repo.remotes.origin.fetch = MagicMock()
    return mock_repo


# ---------------------------------------------------------------------------
# Test: Initialization and clone
# ---------------------------------------------------------------------------


class TestGitPolicyProviderInit:
    """Test GitPolicyProvider initialization."""

    def test_init_stores_config(self):
        """Provider stores repo_url, branch, local_path, fallback_dir."""
        provider = GitPolicyProvider(
            repo_url="https://github.com/example/policies.git",
            branch="main",
            local_path="/tmp/test_repo",
            fallback_dir="/tmp/test_policies",
        )
        assert provider._repo_url == "https://github.com/example/policies.git"
        assert provider._branch == "main"
        assert provider._local_path == "/tmp/test_repo"
        assert provider._fallback_dir == "/tmp/test_policies"

    def test_init_creates_lock(self):
        """Provider creates asyncio.Lock for concurrent access control."""
        provider = GitPolicyProvider(repo_url="https://example.com/repo.git")
        assert isinstance(provider._lock, asyncio.Lock)

    def test_init_empty_cache(self):
        """Provider starts with empty cache."""
        provider = GitPolicyProvider(repo_url="https://example.com/repo.git")
        assert provider._cache == {}


# ---------------------------------------------------------------------------
# Test: get_policies returns parsed policies and HEAD SHA
# ---------------------------------------------------------------------------


class TestGetPolicies:
    """Test get_policies() returns parsed policy dicts and HEAD SHA."""

    @pytest.mark.asyncio
    async def test_returns_policies_and_sha(self):
        """get_policies returns (policies_by_layer, head_sha)."""
        # projects/ layer expects subdirectories per project:
        #   policies/projects/{project_id}/strict.yaml
        proj_tree = MockTree({"strict.yaml": MockBlob(PROJECT_STRICT_YAML)})
        tree = MockTree({
            "policies": MockTree({
                "global": MockTree({"routing.yaml": MockBlob(GLOBAL_ROUTING_YAML)}),
                "projects": MockTree({"proj-001": proj_tree}),
            }),
        })
        mock_repo = _make_mock_repo("abc123", tree)

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_repo_init",
        )
        provider._repo = mock_repo

        policies, sha = await provider.get_policies()

        assert sha == "abc123"
        assert "global" in policies
        assert "projects" in policies
        assert "proj-001" in policies["projects"]
        # Verify global policy has correct structure
        assert policies["global"]["routing.yaml"]["name"] == "global_routing"

    @pytest.mark.asyncio
    async def test_caches_by_sha(self):
        """Second call with same HEAD returns cached result without reading blobs."""
        tree = _make_mock_tree({
            "global": {"routing.yaml": GLOBAL_ROUTING_YAML},
        })
        mock_repo = _make_mock_repo("abc123", tree)
        mock_repo.remotes.origin.fetch = MagicMock()

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_cache",
        )
        provider._repo = mock_repo

        # First call
        policies1, sha1 = await provider.get_policies()
        assert sha1 == "abc123"
        fetch_count_after_first = mock_repo.remotes.origin.fetch.call_count

        # Second call — should use cache
        policies2, sha2 = await provider.get_policies()
        assert sha2 == "abc123"
        # Fetch should not be called again (cached)
        assert mock_repo.remotes.origin.fetch.call_count == fetch_count_after_first
        assert policies1 == policies2

    @pytest.mark.asyncio
    async def test_detects_new_head_updates_cache(self):
        """When HEAD advances, reads new policies and updates cache."""
        tree_v1 = _make_mock_tree({
            "global": {"routing.yaml": GLOBAL_ROUTING_YAML},
        })
        mock_repo = _make_mock_repo("abc123", tree_v1)

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_new_head",
        )
        provider._repo = mock_repo

        # First call
        _, sha1 = await provider.get_policies()
        assert sha1 == "abc123"

        # Simulate HEAD advancing
        tree_v2 = _make_mock_tree({
            "global": {"routing.yaml": GLOBAL_ROUTING_YAML},
            "temporary": {"override.yaml": TEMP_OVERRIDE_YAML},
        })
        mock_repo.head.commit.hexsha = "def456"
        mock_repo.head.commit.tree = tree_v2

        # Second call — should detect new SHA and re-read
        policies2, sha2 = await provider.get_policies()
        assert sha2 == "def456"
        assert "temporary" in policies2


# ---------------------------------------------------------------------------
# Test: get_policies_for_project
# ---------------------------------------------------------------------------


class TestGetPoliciesForProject:
    """Test get_policies_for_project returns global + project-specific."""

    @pytest.mark.asyncio
    async def test_returns_global_and_project_policies(self):
        """Returns combined global + project policies."""
        # Build 3-level tree: policies/projects/{project_id}/file.yaml
        proj_dir = MockTree({"strict.yaml": MockBlob(PROJECT_STRICT_YAML)})
        tree = MockTree({
            "policies": MockTree({
                "global": MockTree({"routing.yaml": MockBlob(GLOBAL_ROUTING_YAML)}),
                "projects": MockTree({"proj-001": proj_dir}),
            }),
        })
        mock_repo = _make_mock_repo("abc123", tree)

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_project",
        )
        provider._repo = mock_repo

        result = await provider.get_policies_for_project("proj-001")

        # Should have global policies
        assert "global" in result
        # Should have project-specific policies
        assert "project" in result
        # Global routing.yaml should be included
        assert any(
            p["name"] == "global_routing" for p in result["global"]
        )

    @pytest.mark.asyncio
    async def test_missing_project_still_returns_global(self):
        """When project has no specific policies, global is still returned."""
        tree = _make_mock_tree({
            "global": {"routing.yaml": GLOBAL_ROUTING_YAML},
        })
        mock_repo = _make_mock_repo("abc123", tree)

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_project_missing",
        )
        provider._repo = mock_repo

        result = await provider.get_policies_for_project("nonexistent-proj")

        assert "global" in result
        assert "project" not in result or result.get("project") == []


# ---------------------------------------------------------------------------
# Test: get_policies_at_commit
# ---------------------------------------------------------------------------


class TestGetPoliciesAtCommit:
    """Test get_policies_at_commit reads from a specific commit (not HEAD)."""

    @pytest.mark.asyncio
    async def test_reads_from_specific_commit(self):
        """get_policies_at_commit reads tree from specified SHA."""
        tree = _make_mock_tree({
            "global": {"routing.yaml": GLOBAL_ROUTING_YAML},
        })

        mock_commit = MagicMock()
        mock_commit.tree = tree

        mock_repo = MagicMock()
        mock_repo.commit.return_value = mock_commit

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_commit",
        )
        provider._repo = mock_repo

        policies, sha = await provider.get_policies_at_commit("specific123")

        mock_repo.commit.assert_called_once_with("specific123")
        assert sha == "specific123"
        assert "global" in policies


# ---------------------------------------------------------------------------
# Test: Fallback to local directory
# ---------------------------------------------------------------------------


class TestFallbackToLocal:
    """Test fallback behavior when git_repo_url is empty."""

    @pytest.mark.asyncio
    async def test_fallback_reads_local_yaml(self, tmp_path):
        """When repo_url is empty, reads from local fallback_dir."""
        # Create local YAML files
        policies_dir = tmp_path / "policies"
        policies_dir.mkdir()

        yaml_content = yaml.dump({
            "name": "local_policy",
            "version": "1.0",
            "rules": [
                {
                    "name": "auto_all",
                    "priority": 1,
                    "conditions": {
                        "operator": "AND",
                        "checks": [
                            {"field": "project_id", "operator": "equals", "value": "any"},
                        ],
                    },
                    "disposition": "AUTO",
                },
            ],
        })
        (policies_dir / "routing.yaml").write_text(yaml_content)

        provider = GitPolicyProvider(
            repo_url="",
            fallback_dir=str(policies_dir),
        )

        policies, sha = await provider.get_policies()

        assert sha == "local"
        assert "local" in policies
        assert len(policies["local"]) >= 1

    @pytest.mark.asyncio
    async def test_fallback_returns_local_sha(self, tmp_path):
        """Fallback mode returns 'local' as the SHA."""
        policies_dir = tmp_path / "empty_policies"
        policies_dir.mkdir()

        provider = GitPolicyProvider(
            repo_url="",
            fallback_dir=str(policies_dir),
        )

        policies, sha = await provider.get_policies()

        assert sha == "local"


# ---------------------------------------------------------------------------
# Test: Concurrent access with asyncio.Lock
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    """Test asyncio.Lock prevents parallel fetch operations."""

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_fetch(self):
        """Concurrent get_policies calls are serialized via lock."""
        tree = _make_mock_tree({
            "global": {"routing.yaml": GLOBAL_ROUTING_YAML},
        })
        mock_repo = _make_mock_repo("abc123", tree)

        provider = GitPolicyProvider(
            repo_url="https://example.com/repo.git",
            local_path="/tmp/test_concurrent",
        )
        provider._repo = mock_repo

        # Run two get_policies calls concurrently
        results = await asyncio.gather(
            provider.get_policies(),
            provider.get_policies(),
        )

        # Both should succeed
        assert len(results) == 2
        assert results[0][1] == "abc123"
        assert results[1][1] == "abc123"


# ---------------------------------------------------------------------------
# Test: Singleton factory
# ---------------------------------------------------------------------------


class TestGetGitPolicyProvider:
    """Test the module-level singleton factory."""

    def test_returns_git_policy_provider(self):
        """Factory returns a GitPolicyProvider instance."""
        provider = get_git_policy_provider(
            repo_url="https://example.com/repo.git",
        )
        assert isinstance(provider, GitPolicyProvider)
