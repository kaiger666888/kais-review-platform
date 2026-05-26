"""Dual-write audit recorder for PostgreSQL + MinIO JSONL archival.

Writes audit entries to PostgreSQL in real-time (via existing AuditLogger)
and asynchronously archives them to MinIO as JSONL for warm/cold tier storage.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _get_minio_client():
    """Create MinIO client from settings. Returns None if not configured."""
    try:
        from minio import MinIO
    except ImportError:
        logger.warning("minio_package_not_installed")
        return None

    settings = get_settings()
    if not settings.minio_access_key or not settings.minio_secret_key:
        return None
    return MinIO(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


class DualWriteAuditRecorder:
    """Archives AuditEntry rows to MinIO as JSONL and reads them back.

    The archive path structure is::

        audit-archive/{year}/{month}/{day}/entries_{first_id}_{last_id}.jsonl

    Each line in the JSONL file is a JSON object with fields:
        id, review_id, action, actor, from_state, to_state,
        payload, prev_hash, own_hash, created_at (ISO format).
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def archive_entries_to_minio(self, entries: list[Any]) -> int:
        """Serialize audit entries as JSONL and write to MinIO.

        Args:
            entries: List of AuditEntry ORM objects.

        Returns:
            Number of entries archived.
        """
        if not entries:
            return 0

        client = _get_minio_client()
        if client is None:
            logger.warning("dual_write_minio_not_configured")
            return 0

        # Ensure bucket exists
        bucket = self._settings.minio_bucket
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
        except Exception as exc:
            logger.error("dual_write_bucket_check_failed", error=str(exc))
            return 0

        # Serialize entries to JSONL
        lines: list[str] = []
        for entry in entries:
            record = {
                "id": entry.id,
                "review_id": entry.review_id,
                "action": entry.action,
                "actor": entry.actor,
                "from_state": entry.from_state,
                "to_state": entry.to_state,
                "payload": entry.payload,
                "prev_hash": entry.prev_hash,
                "own_hash": entry.own_hash,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            lines.append(json.dumps(record, default=str))

        # Determine object path from first entry's created_at
        first = entries[0]
        created = first.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        year = created.strftime("%Y")
        month = created.strftime("%m")
        day = created.strftime("%d")
        last = entries[-1]

        object_name = (
            f"audit-archive/{year}/{month}/{day}/"
            f"entries_{first.id}_{last.id}.jsonl"
        )

        # Write to MinIO
        content = "\n".join(lines).encode("utf-8")
        data_stream = BytesIO(content)
        data_length = len(content)

        try:
            client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=data_stream,
                length=data_length,
                content_type="application/x-ndjson",
            )
            logger.info(
                "dual_write_archived",
                count=len(entries),
                object_name=object_name,
            )
            return len(entries)
        except Exception as exc:
            logger.error("dual_write_minio_write_failed", error=str(exc))
            return 0

    async def query_warm_storage(
        self, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Query archived audit entries from MinIO within a date range.

        Lists objects in MinIO under audit-archive/{year}/{month}/{day}/
        for each date in the range, reads each JSONL object, and returns
        a flattened list of dicts.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            List of audit entry dicts from warm storage.
        """
        client = _get_minio_client()
        if client is None:
            return []

        bucket = self._settings.minio_bucket
        results: list[dict[str, Any]] = []

        # Iterate through each date in range
        current = start_date
        while current <= end_date:
            prefix = f"audit-archive/{current.strftime('%Y/%m/%d')}/"
            try:
                objects = client.list_objects(bucket, prefix=prefix, recursive=True)
                for obj in objects:
                    try:
                        response = client.get_object(bucket, obj.object_name)
                        content = response.read().decode("utf-8")
                        response.close()
                        response.release_conn()
                        for line in content.strip().split("\n"):
                            if line.strip():
                                results.append(json.loads(line))
                    except Exception as exc:
                        logger.warning(
                            "dual_write_read_object_failed",
                            object_name=obj.object_name,
                            error=str(exc),
                        )
            except Exception as exc:
                logger.warning(
                    "dual_write_list_objects_failed",
                    prefix=prefix,
                    error=str(exc),
                )

            # Move to next day
            current = current + timedelta(days=1)

        return results
