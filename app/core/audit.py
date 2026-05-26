import hashlib
import sqlite3

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schema import AuditEntry


def audit_protect_authorizer(action, arg1, arg2, arg3, arg4):
    """SQLite authorizer that blocks UPDATE and DELETE on audit_entries table."""
    if action == sqlite3.SQLITE_UPDATE and arg1 == "audit_entries":
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_DELETE and arg1 == "audit_entries":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class AuditLogger:
    """Immutable audit logger with SHA-256 hash chain."""

    async def log(
        self,
        session: AsyncSession,
        review_id: int,
        action: str,
        actor: str,
        from_state: str | None = None,
        to_state: str | None = None,
        payload: dict | None = None,
    ) -> AuditEntry:
        # Get previous hash from the last audit entry for this review
        stmt = (
            select(AuditEntry)
            .where(AuditEntry.review_id == review_id)
            .order_by(AuditEntry.id.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        last_entry = result.scalar_one_or_none()

        prev_hash = last_entry.own_hash if last_entry else "0" * 64

        # Create entry with placeholder hash
        entry = AuditEntry(
            review_id=review_id,
            action=action,
            actor=actor,
            from_state=from_state,
            to_state=to_state,
            payload=payload,
            prev_hash=prev_hash,
            own_hash="pending",
        )
        session.add(entry)
        await session.flush()

        # Compute own_hash from entry fields
        hash_input = (
            f"{entry.id}:{entry.review_id}:{entry.action}:{entry.actor}:"
            f"{entry.from_state}:{entry.to_state}:{entry.prev_hash}:"
            f"{entry.created_at.isoformat()}"
        )
        own_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        entry.own_hash = own_hash

        await session.commit()
        return entry


async def append_audit(
    session: AsyncSession,
    review_id: int,
    action: str,
    actor: str,
    **kwargs,
) -> AuditEntry:
    """Convenience function to append an audit entry."""
    logger = AuditLogger()
    return await logger.log(session, review_id, action, actor, **kwargs)
