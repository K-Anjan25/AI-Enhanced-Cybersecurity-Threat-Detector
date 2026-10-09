"""PostgreSQL-backed audit trail.

Replaces InMemoryAuditTrail with persistent storage using the audit_log table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLog
from app.services.audit_log import AuditAction, AuditEntry, AuditTrail

__all__ = ["PostgresAuditTrail", "AuditTrailUnavailable"]


class AuditTrailUnavailable(RuntimeError):
    """Raised when the audit trail cannot fulfill a request."""


class PostgresAuditTrail:
    """Persistent audit trail backed by PostgreSQL.

    Append-only per R-31: no update, no delete.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def record(
        self,
        action: AuditAction | str,
        actor: str,
        target_type: str,
        target_id: str,
        at: datetime | None = None,
        detail: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> None:
        """Append one audit entry."""
        try:
            async with self._sessions() as session:
                await session.execute(
                    insert(AuditLog).values(
                        actor_id=0,  # Will be resolved from actor string
                        action=action.value if isinstance(action, AuditAction) else action,
                        target_type=target_type,
                        target_id=target_id,
                        detail=detail or {},
                        ip=ip,
                        at=at or datetime.now(UTC),
                    )
                )
                await session.commit()
        except SQLAlchemyError as exc:
            raise AuditTrailUnavailable(str(exc)) from exc

    async def query(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read audit entries within a time range."""
        try:
            async with self._sessions() as session:
                stmt = select(AuditLog).order_by(AuditLog.at.desc())
                if start:
                    stmt = stmt.where(AuditLog.at >= start)
                if end:
                    stmt = stmt.where(AuditLog.at < end)
                stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                return [
                    {
                        "id": row.id,
                        "action": row.action,
                        "actor": str(row.actor_id),
                        "target_type": row.target_type,
                        "target_id": row.target_id,
                        "detail": row.detail,
                        "ip": str(row.ip) if row.ip else None,
                        "at": row.at.isoformat() if row.at else None,
                    }
                    for row in result.scalars()
                ]
        except SQLAlchemyError as exc:
            raise AuditTrailUnavailable(str(exc)) from exc