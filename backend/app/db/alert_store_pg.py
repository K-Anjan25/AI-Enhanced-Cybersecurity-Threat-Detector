"""PostgreSQL-backed alert store.

Replaces InMemoryAlertStore with persistent storage using the alerts table.
The schema is in db/models.py (Alert model).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Alert, AlertStatus, Entity, Severity
from app.db.repository import MAX_QUERY_SPAN_DAYS, TimeRange
from app.schemas.query import AlertQuery
from app.services.alert_store import AlertStore
from app.services.overview import (
    BUCKET_MINUTES_DEFAULT,
    ENTITY_LIMIT_DEFAULT,
    FAMILY_LIMIT_DEFAULT,
    Aggregate,
    OverviewBucket,
    OverviewEntity,
    OverviewFamily,
    OverviewTotals,
)

__all__ = ["PostgresAlertStore", "AlertStoreUnavailable"]


class AlertStoreUnavailable(RuntimeError):
    """Raised when the alert store cannot fulfill a request."""


class PostgresAlertStore:
    """Persistent alert store backed by PostgreSQL.

    Writes go to the alerts table; reads use the same SQL predicates
    the in-memory store re-states in Python.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def save(self, case_id: str, values: Mapping[str, object], *, created_at: datetime) -> Alert:
        """Store one alert, replacing any earlier row for the same case.

        The case_id is stored in window_ref.id for upsert lookup.
        """
        try:
            async with self._sessions() as session:
                # Check if alert with this case_id already exists
                window_ref = values.get("window_ref", {})
                if isinstance(window_ref, dict):
                    evidence_id = window_ref.get("id", case_id)
                else:
                    evidence_id = case_id

                # Try to find existing alert by matching window_ref->>'id'
                existing = await session.execute(
                    select(Alert).where(
                        Alert.window_ref["id"].astext == evidence_id,
                        Alert.status != AlertStatus.closed,
                    ).limit(1)
                )
                row = existing.scalar_one_or_none()

                if row is not None:
                    # Update existing
                    for key, val in values.items():
                        if hasattr(row, key) and key not in ("id", "created_at"):
                            setattr(row, key, val)
                    await session.commit()
                    await session.refresh(row)
                    return row
                else:
                    # Insert new
                    stmt = insert(Alert).values(
                        created_at=created_at,
                        **{k: v for k, v in values.items() if hasattr(Alert, k)},
                    ).returning(Alert)
                    result = await session.execute(stmt)
                    await session.commit()
                    row = result.scalar_one()
                    return row
        except SQLAlchemyError as exc:
            raise AlertStoreUnavailable(str(exc)) from exc

    async def fetch(self, query: AlertQuery) -> list[Alert]:
        """Return alerts matching the query."""
        try:
            async with self._sessions() as session:
                stmt = select(Alert)

                # Time bounds (R-34)
                if query.start:
                    stmt = stmt.where(Alert.created_at >= query.start)
                if query.end:
                    stmt = stmt.where(Alert.created_at < query.end)

                # Filters
                if query.severity:
                    stmt = stmt.where(Alert.severity == query.severity)
                if query.status:
                    stmt = stmt.where(Alert.status == query.status)
                if query.family:
                    stmt = stmt.where(Alert.family == query.family)
                if query.entity_id is not None:
                    stmt = stmt.where(Alert.entity_id == query.entity_id)
                if query.min_score is not None:
                    stmt = stmt.where(Alert.score >= Decimal(str(query.min_score)))

                # Order
                if query.order == "desc":
                    stmt = stmt.order_by(Alert.created_at.desc(), Alert.id.desc())
                else:
                    stmt = stmt.order_by(Alert.created_at.asc(), Alert.id.asc())

                # Limit
                stmt = stmt.limit(query.limit + 1)

                result = await session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise AlertStoreUnavailable(str(exc)) from exc

    async def get(self, alert_id: int, partition_key: datetime) -> Alert | None:
        """Get one alert by id and partition key."""
        try:
            async with self._sessions() as session:
                result = await session.execute(
                    select(Alert).where(
                        Alert.id == alert_id,
                        Alert.created_at == partition_key,
                    )
                )
                return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise AlertStoreUnavailable(str(exc)) from exc

    async def aggregate(
        self,
        window: TimeRange,
        *,
        bucket_minutes: int = BUCKET_MINUTES_DEFAULT,
        entity_limit: int = ENTITY_LIMIT_DEFAULT,
        family_limit: int = FAMILY_LIMIT_DEFAULT,
    ) -> Aggregate:
        """Aggregate alerts in the window for the overview page."""
        try:
            async with self._sessions() as session:
                # Totals
                totals_stmt = select(
                    func.count(Alert.id).label("alerts"),
                    func.count(Alert.id).filter(Alert.status == AlertStatus.open).label("open"),
                ).where(
                    Alert.created_at >= window.start,
                    Alert.created_at < window.end,
                )
                totals_result = await session.execute(totals_stmt)
                totals_row = totals_result.one()

                # Severity breakdown
                severity_stmt = select(
                    Alert.severity,
                    func.count(Alert.id),
                ).where(
                    Alert.created_at >= window.start,
                    Alert.created_at < window.end,
                ).group_by(Alert.severity)
                severity_result = await session.execute(severity_stmt)
                by_severity = {row[0]: row[1] for row in severity_result}

                # Series buckets
                bucket_width = f"{bucket_minutes} minutes"
                series_stmt = select(
                    func.date_bin(bucket_width, Alert.created_at, window.start).label("bucket"),
                    func.count(Alert.id).label("count"),
                ).where(
                    Alert.created_at >= window.start,
                    Alert.created_at < window.end,
                ).group_by("bucket").order_by("bucket")
                series_result = await session.execute(series_stmt)
                series = [
                    OverviewBucket(start=row.bucket, total=row.count, by_severity={})
                    for row in series_result
                ]

                # Top entities
                entity_stmt = select(
                    Alert.entity_id,
                    func.count(Alert.id).label("alerts"),
                    func.max(Alert.severity).label("worst"),
                ).where(
                    Alert.created_at >= window.start,
                    Alert.created_at < window.end,
                ).group_by(Alert.entity_id).order_by(func.count(Alert.id).desc()).limit(entity_limit)
                entity_result = await session.execute(entity_stmt)
                entities = [
                    OverviewEntity(
                        entity_id=row.entity_id,
                        kind=None,
                        value=None,
                        named=False,
                        alerts=row.alerts,
                        occurrences=row.alerts,
                        open=0,
                        worst_severity=row.worst,
                        max_score=0,
                        last_seen="",
                    )
                    for row in entity_result
                ]

                # Family mix
                family_stmt = select(
                    Alert.family,
                    func.count(Alert.id).label("alerts"),
                    func.max(Alert.severity).label("worst"),
                ).where(
                    Alert.created_at >= window.start,
                    Alert.created_at < window.end,
                ).group_by(Alert.family).order_by(func.count(Alert.id).desc()).limit(family_limit)
                family_result = await session.execute(family_stmt)
                families = [
                    OverviewFamily(
                        family=row.family,
                        alerts=row.alerts,
                        worst_severity=row.worst,
                    )
                    for row in family_result
                ]

                return Aggregate(
                    totals=OverviewTotals(
                        alerts=totals_row.alerts,
                        open=totals_row.open,
                        by_severity=by_severity,
                        unrecognised_severity=0,
                        verdicts={},
                        unrecorded=0,
                        verdicts_measured=0,
                        mean_time_to_verdict_seconds=None,
                    ),
                    series=series,
                    entities=entities,
                    entities_capped=False,
                    families=families,
                    families_capped=False,
                )
        except SQLAlchemyError as exc:
            raise AlertStoreUnavailable(str(exc)) from exc