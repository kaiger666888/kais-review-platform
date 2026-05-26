"""Git-backed policy provider with SHA-based caching.

Reads YAML policy files from a Git governance repository, organized into
layers (global, projects/{id}, temporary). Policies are cached by commit
SHA so that unchanged HEADs avoid redundant Git operations.

When git_repo_url is empty, falls back to reading YAML files from a local
directory (V1 backward compatibility).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from app.core.policy import PolicyEngine

logger = logging.getLogger(__name__)


class GitPolicyProvider:
    """Provides policy files from a Git repository with SHA-based caching.

    The expected repo structure is::

        policies/
          global/
            routing.yaml
          projects/
            {project_id}/
              strict.yaml
          temporary/
            override.yaml

    Usage::

        provider = GitPolicyProvider(
            repo_url="https://github.com/org/policy-repo.git",
            branch="main",
        )
        policies, sha = await provider.get_policies()
    """

    def __init__(
        self,
        repo_url: str,
        branch: str = "main",
        local_path: str = ".policy_repo",
        fallback_dir: str = "app/policies",
    ) -> None:
        self._repo_url = repo_url
        self._branch = branch
        self._local_path = local_path
        self._fallback_dir = fallback_dir
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[dict[str, Any], str]] = {}
        self._repo: Any = None

    # -- Repo Management -----------------------------------------------------

    async def _ensure_repo(self) -> Any:
        """Ensure the local Git repo exists and is up-to-date.

        Clones the repo if local_path doesn't exist, otherwise fetches
        the latest from origin. Uses asyncio.Lock to prevent concurrent
        operations.

        Returns:
            git.Repo instance.
        """
        async with self._lock:
            if self._repo is not None:
                return self._repo

            import git

            local = Path(self._local_path)
            if local.exists() and (local / ".git").exists():
                self._repo = git.Repo(str(local))
                self._repo.remotes.origin.fetch()
            else:
                self._repo = git.Repo.clone_from(
                    self._repo_url, str(local), branch=self._branch
                )
            return self._repo

    # -- Policy Reading ------------------------------------------------------

    def _read_yaml_from_tree(self, tree: Any, path_parts: list[str]) -> dict | None:
        """Navigate a Git tree and parse a YAML file.

        Args:
            tree: A git.Tree object (or mock with dict-like access).
            path_parts: Path segments to navigate, e.g. ["policies", "global", "routing.yaml"].

        Returns:
            Parsed YAML dict, or None if file not found or parse error.
        """
        try:
            current = tree
            for part in path_parts:
                current = current[part]
            content = current.data_stream.read().decode("utf-8")
            return yaml.safe_load(content)
        except (KeyError, AttributeError, yaml.YAMLError) as exc:
            logger.debug("Failed to read %s from tree: %s", "/".join(path_parts), exc)
            return None

    def _read_layer_from_tree(
        self, tree: Any, layer_path: str
    ) -> dict[str, dict]:
        """Read all YAML files from a tree path (e.g. policies/global/).

        Args:
            tree: Git tree object.
            layer_path: Slash-separated path within the tree.

        Returns:
            Dict of {filename: parsed_yaml_dict}.
        """
        policies: dict[str, dict] = {}
        parts = layer_path.split("/")

        try:
            current = tree
            for part in parts:
                current = current[part]

            # current is now a tree (directory) — iterate its blobs
            if hasattr(current, "__iter__"):
                for item in current:
                    name = item[0] if isinstance(item, tuple) else getattr(item, "name", str(item))
                    if isinstance(name, str) and name.endswith(".yaml"):
                        blob = current[name] if not isinstance(item, tuple) else item[1]
                        content = blob.data_stream.read().decode("utf-8")
                        parsed = yaml.safe_load(content)
                        if isinstance(parsed, dict):
                            policies[name] = parsed
        except (KeyError, AttributeError) as exc:
            logger.debug("Layer %s not found in tree: %s", layer_path, exc)

        return policies

    def _read_all_policies_from_tree(self, tree: Any) -> dict[str, dict[str, dict]]:
        """Read all policy layers from a Git tree.

        Returns:
            Dict of {layer_name: {filename: parsed_yaml}}.
        """
        result: dict[str, dict[str, dict]] = {}

        # Global layer
        global_policies = self._read_layer_from_tree(tree, "policies/global")
        if global_policies:
            result["global"] = global_policies

        # Projects layer (may contain subdirectories per project)
        try:
            current = tree
            for part in ["policies", "projects"]:
                current = current[part]

            if hasattr(current, "__iter__"):
                for item in current:
                    name = item[0] if isinstance(item, tuple) else getattr(item, "name", str(item))
                    if isinstance(name, str):
                        # Each subdirectory is a project
                        project_policies = self._read_layer_from_tree(
                            tree, f"policies/projects/{name}"
                        )
                        if project_policies:
                            result.setdefault("projects", {})[name] = project_policies
        except (KeyError, AttributeError):
            pass

        # Temporary layer
        temp_policies = self._read_layer_from_tree(tree, "policies/temporary")
        if temp_policies:
            result["temporary"] = temp_policies

        return result

    # -- Public API ----------------------------------------------------------

    async def get_policies(self) -> tuple[dict[str, Any], str]:
        """Get current policies from the Git repo.

        Returns:
            Tuple of (policies_by_layer, head_commit_sha).
            When falling back to local: ({"local": [...]}, "local").
        """
        # Fallback to local directory
        if not self._repo_url:
            return await self._get_local_policies()

        repo = await self._ensure_repo()

        head_sha = repo.head.commit.hexsha

        # Check cache
        if head_sha in self._cache:
            cached_policies, cached_sha = self._cache[head_sha]
            return cached_policies, cached_sha

        # Read from tree
        tree = repo.head.commit.tree
        policies = self._read_all_policies_from_tree(tree)

        # Cache
        self._cache[head_sha] = (policies, head_sha)
        return policies, head_sha

    async def _get_local_policies(self) -> tuple[dict[str, Any], str]:
        """Read policies from local fallback directory."""
        fallback = Path(self._fallback_dir)
        local_policies: list[dict] = []

        if fallback.exists():
            engine = PolicyEngine()
            for yaml_file in sorted(fallback.glob("*.yaml")):
                try:
                    content = yaml_file.read_text()
                    data = yaml.safe_load(content)
                    if isinstance(data, dict):
                        local_policies.append(data)
                except yaml.YAMLError:
                    logger.warning("Failed to parse local policy: %s", yaml_file)

        return {"local": local_policies}, "local"

    async def get_policies_for_project(
        self, project_id: str
    ) -> dict[str, list[dict]]:
        """Get global + project-specific policies for a given project.

        Args:
            project_id: Project identifier.

        Returns:
            Dict with "global" (list of policy dicts) and optionally
            "project" (list of project-specific policy dicts).
        """
        all_policies, _sha = await self.get_policies()
        result: dict[str, list[dict]] = {}

        # Global policies
        if "global" in all_policies:
            result["global"] = list(all_policies["global"].values())

        # Project-specific policies
        if "projects" in all_policies and project_id in all_policies["projects"]:
            project_layer = all_policies["projects"][project_id]
            result["project"] = list(project_layer.values())

        return result

    async def get_policies_at_commit(
        self, commit_sha: str
    ) -> tuple[dict[str, Any], str]:
        """Read policies from a specific commit (not HEAD).

        Useful for audit trail verification.

        Args:
            commit_sha: Full or abbreviated commit SHA.

        Returns:
            Tuple of (policies_by_layer, commit_sha).
        """
        if not self._repo_url:
            return await self._get_local_policies()

        repo = await self._ensure_repo()
        commit = repo.commit(commit_sha)
        policies = self._read_all_policies_from_tree(commit.tree)

        return policies, commit_sha


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------

_provider: GitPolicyProvider | None = None


def get_git_policy_provider(
    repo_url: str = "",
    branch: str = "main",
    local_path: str = ".policy_repo",
    fallback_dir: str = "app/policies",
) -> GitPolicyProvider:
    """Return or create the global GitPolicyProvider singleton.

    Args:
        repo_url: Git repository URL (empty for local fallback).
        branch: Git branch to track.
        local_path: Local directory for the cloned repo.
        fallback_dir: Local directory for YAML files when repo_url is empty.

    Returns:
        GitPolicyProvider instance.
    """
    global _provider
    if _provider is None:
        _provider = GitPolicyProvider(
            repo_url=repo_url,
            branch=branch,
            local_path=local_path,
            fallback_dir=fallback_dir,
        )
    return _provider
