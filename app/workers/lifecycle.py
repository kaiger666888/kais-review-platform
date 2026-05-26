"""Tiered storage lifecycle management cron workers.

archive_hot_to_warm: Archives audit entries older than hot_retention_days
    from PostgreSQL to MinIO JSONL, then deletes the archived rows.

compute_merkle_root_cron: Computes the Merkle root for yesterday's audit
    entries and commits it to the Git governance repository.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.dual_write import DualWriteAuditRecorder
from app.core.merkle import commit_merkle_root_to_git, compute_daily_merkle_root
from app.models.schema import AuditEntry

logger = structlog.get_logger(__name__)

# Maximum number of entries to archive per batch (avoids memory spikes)
BATCH_SIZE = 500


async def archive_hot_to_warm(ctx: dict) -> dict[str, Any]:
    """Archive audit entries from hot (PostgreSQL) to warm (MinIO) storage.

    Queries AuditEntry rows where created_at is older than hot_retention_days
    (from settings), archives them to MinIO JSONL in batches of 500, then
    deletes the archived rows from PostgreSQL.

    Called daily at 02:00 UTC via arq cron.

    Args:
        ctx: arq context dict.

    Returns:
        Dict with archived count and batch count.
    """
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.hot_retention_days)

    recorder = DualWriteAuditRecorder()
    total_archived = 0
    batch_count = 0

    while True:
        async with async_session_factory() as session:
            stmt = (
                select(AuditEntry)
                .where(AuditEntry.created_at < cutoff)
                .order_by(AuditEntry.id.asc())
                .limit(BATCH_SIZE)
            )
            result = await session.execute(stmt)
            batch = result.scalars().all()

            if not batch:
                break

            batch_ids = [entry.id for entry in batch]

        # Archive to MinIO
        archived = await recorder.archive_entries_to_minio(batch)
        if archived == 0:
            logger.error(
                "archive_hot_to_warm_minio_failed",
                batch=batch_count + 1,
                entry_count=len(batch),
            )
            break

        # Delete archived rows from PostgreSQL
        async with async_session_factory() as session:
            await session.execute(
                delete(AuditEntry).where(AuditEntry.id.in_(batch_ids))
            )
            await session.commit()

        total_archived += archived
        batch_count += 1

        logger.info(
            "archive_hot_to_warm_batch",
            batch=batch_count,
            archived=archived,
            total=total_archived,
        )

    logger.info(
        "archive_hot_to_warm_complete",
        total_archived=total_archived,
        batches=batch_count,
    )
    return {"archived": total_archived, "batches": batch_count}


async def compute_merkle_root_cron(ctx: dict) -> dict[str, Any]:
    """Compute yesterday's Merkle root and commit to Git.

    Called daily at 00:30 UTC via arq cron (after midnight so all
    entries for the day are in).

    Args:
        ctx: arq context dict.

    Returns:
        Dict with date, root hash, and git commit SHA.
    """
    target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # Compute Merkle root from audit entries
    merkle_data = await compute_daily_merkle_root(target_date)
    root_hash = merkle_data["root"]

    logger.info(
        "merkle_root_computed",
        date=target_date.isoformat(),
        root=root_hash,
        leaf_count=merkle_data["leaf_count"],
    )

    # Commit to Git governance repo
    git_sha = await commit_merkle_root_to_git(merkle_data)

    if git_sha:
        logger.info(
            "merkle_root_cron_success",
            date=target_date.isoformat(),
            git_commit=git_sha,
        )
    else:
        logger.warning(
            "merkle_root_cron_git_failed",
            date=target_date.isoformat(),
            note="Root computed but not anchored to Git",
        )

    return {
        "date": target_date.isoformat(),
        "root": root_hash,
        "git_commit_sha": git_sha,
    }
