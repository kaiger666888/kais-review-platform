"""Merkle tree computation and Git anchoring for tamper-evident audit logs.

Builds a daily binary Merkle tree from audit entry hashes and commits
the root to the Git governance repository, enabling cryptographic
verification of audit log integrity.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.models.schema import AuditEntry

logger = structlog.get_logger(__name__)


class MerkleTree:
    """Binary Merkle tree built from ordered leaf hashes.

    Usage::

        tree = MerkleTree(["hash_a", "hash_b", "hash_c"])
        root = tree.build()  # 64-char hex string
        MerkleTree.verify(["hash_a", "hash_b", "hash_c"], root)  # True
    """

    def __init__(self, hashes: list[str]) -> None:
        self._leaves = list(hashes)

    def build(self) -> str:
        """Build binary Merkle tree and return the root hash.

        If the number of leaves is odd, the last leaf is duplicated.
        Each non-leaf node = SHA-256(left_child_hex + right_child_hex).

        Returns:
            64-character hex string (SHA-256 digest).
        """
        if not self._leaves:
            return hashlib.sha256(b"").hexdigest()

        current_level = list(self._leaves)

        while len(current_level) > 1:
            if len(current_level) % 2 == 1:
                current_level.append(current_level[-1])

            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                combined = current_level[i] + current_level[i + 1]
                parent_hash = hashlib.sha256(combined.encode()).hexdigest()
                next_level.append(parent_hash)
            current_level = next_level

        return current_level[0]

    def get_leaves(self) -> list[str]:
        """Return the original leaf hashes."""
        return list(self._leaves)

    @staticmethod
    def verify(leaves: list[str], expected_root: str) -> bool:
        """Rebuild the tree from leaves and compare root.

        Args:
            leaves: Ordered list of leaf hash strings.
            expected_root: The expected Merkle root (64-char hex).

        Returns:
            True if the recomputed root matches expected_root.
        """
        tree = MerkleTree(leaves)
        return tree.build() == expected_root


async def compute_daily_merkle_root(target_date: date) -> dict[str, Any]:
    """Compute the Merkle root for all audit entries on a given date.

    Queries AuditEntry rows where created_at falls on target_date (UTC),
    builds a Merkle tree from their hashes, and returns the result.

    Args:
        target_date: The UTC date to compute the root for.

    Returns:
        Dict with date, root, leaf_count, and leaves.
    """
    from app.core.database import async_session_factory

    start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    end = datetime(
        target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999,
        tzinfo=timezone.utc,
    )

    async with async_session_factory() as session:
        stmt = (
            select(AuditEntry)
            .where(AuditEntry.created_at >= start, AuditEntry.created_at <= end)
            .order_by(AuditEntry.created_at.asc())
        )
        result = await session.execute(stmt)
        entries = result.scalars().all()

    leaf_hashes: list[str] = []
    for entry in entries:
        leaf = hashlib.sha256(f"{entry.id}:{entry.own_hash}".encode()).hexdigest()
        leaf_hashes.append(leaf)

    tree = MerkleTree(leaf_hashes)
    root = tree.build()

    return {
        "date": target_date.isoformat(),
        "root": root,
        "leaf_count": len(leaf_hashes),
        "leaves": leaf_hashes,
    }


async def commit_merkle_root_to_git(merkle_data: dict[str, Any]) -> str | None:
    """Commit a Merkle root JSON file to the Git governance repository.

    Writes the merkle_data dict as JSON to audit_merkle/merkle_{date}.json
    in the governance repo, then stages and commits the file.

    Args:
        merkle_data: Dict with date, root, leaf_count, leaves.

    Returns:
        Commit SHA hex string, or None if Git is not configured or fails.
    """
    settings = get_settings()

    if not settings.git_repo_url:
        logger.warning("merkle_git_skip_no_repo_url")
        return None

    try:
        import git

        local_path = Path(".policy_repo")
        target_date = merkle_data["date"]

        if local_path.exists() and (local_path / ".git").exists():
            repo = git.Repo(str(local_path))
        else:
            logger.warning("merkle_git_repo_not_found", path=str(local_path))
            return None

        # Write merkle data as JSON
        merkle_dir = local_path / "audit_merkle"
        merkle_dir.mkdir(exist_ok=True)
        merkle_file = merkle_dir / f"merkle_{target_date}.json"
        merkle_file.write_text(json.dumps(merkle_data, indent=2))

        # Stage and commit
        relative_path = f"audit_merkle/merkle_{target_date}.json"
        repo.index.add([relative_path])
        commit = repo.index.commit(f"audit: merkle root for {target_date}")

        logger.info(
            "merkle_root_committed_to_git",
            date=target_date,
            commit_sha=commit.hexsha,
        )
        return commit.hexsha

    except Exception as exc:
        logger.error("merkle_git_commit_failed", error=str(exc))
        return None
