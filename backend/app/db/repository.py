r"""Repository layer that makes unbounded scans unrepresentable (T-301, R-34).

R-34 says the time-partitioned tables are only queried with a time-range
predicate. On a monthly-partitioned table that is not a style preference: a query
with no time predicate does not read one partition, it reads every partition that
retention has not yet dropped, which on a system that has run for a year is the
whole archive.

Two layers, because either one alone has a hole.

**A range is required to build the query.** :func:`query_partitioned` takes the
:class:`TimeRange` as a positional argument, so there is no call shape that omits
it. :class:`TimeRange` validates on construction: an inverted or open-ended range
cannot exist, and neither can one wider than ``MAX_QUERY_SPAN_DAYS``.

**A hand-built statement is inspected before it runs.** The constructor cannot
stop a caller assembling a ``select()`` by hand, so :func:`assert_time_bounded`
walks the statement's FROM clause and its WHERE predicates and refuses any
partitioned table whose partition column is not constrained. That is the layer
that catches the case R-34 actually worries about — someone who knows the API and
goes around it.

Both raise :class:`UnboundedScanError` naming the table and the column, because
"query rejected" without saying which predicate is missing just gets the check
deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, case, func, select
from sqlalchemy.sql.elements import BinaryExpression

from app.db.models import PARTITION_KEYS, PARTITIONED_TABLES

#: A ``Select`` of any column shape -- the shape is the caller's, and ``Select``'s
#: parameters are the columns themselves, so the shape has to be packed.
_SelectAny = Select[*tuple[Any, ...]]
#: A ``Select`` of any column shape, bound for a type variable.
_Statement = TypeVar("_Statement", bound=_SelectAny)

#: Widest range a single query may cover. A year of monthly partitions is the
#: archive, and a query allowed to span it is the unbounded scan R-34 forbids,
#: just written with a predicate attached.
MAX_QUERY_SPAN_DAYS = 92


class UnboundedScanError(RuntimeError):
    """Raised when a query against a partitioned table has no time predicate."""


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A bounded, non-empty time window.

    Attributes:
        start: inclusive lower bound.
        end: exclusive upper bound.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Refuse a range that cannot prune partitions."""
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError(
                "both bounds must be timezone-aware; a naive timestamp compared "
                "against a timestamptz column is interpreted in the session "
                "timezone, which moves the partition boundary"
            )
        if self.end <= self.start:
            raise ValueError(
                f"the range is empty or inverted: start {self.start.isoformat()} "
                f"must precede end {self.end.isoformat()}"
            )
        span = self.end - self.start
        if span > timedelta(days=MAX_QUERY_SPAN_DAYS):
            raise ValueError(
                f"the range spans {span.days} days, over the {MAX_QUERY_SPAN_DAYS}-day "
                "limit. A query allowed to cover the whole archive is the unbounded "
                "scan R-34 forbids, with a predicate attached; narrow it or page it."
            )

    @property
    def span(self) -> timedelta:
        """How wide the range is."""
        return self.end - self.start


def _partition_columns_in(clause: object) -> set[str]:
    """Names of partition columns constrained anywhere in a WHERE clause."""
    found: set[str] = set()
    if clause is None:
        return found
    if isinstance(clause, BinaryExpression):
        for side in (clause.left, clause.right):
            name = getattr(side, "name", None)
            table = getattr(getattr(side, "table", None), "name", None)
            if name in PARTITION_KEYS.values() and table in PARTITIONED_TABLES:
                found.add(f"{table}.{name}")
        for side in (clause.left, clause.right):
            found |= _partition_columns_in(side)
        return found
    for child in getattr(clause, "clauses", ()) or ():
        found |= _partition_columns_in(child)
    for operand in (
        getattr(clause, "left", None),
        getattr(clause, "right", None),
    ):
        if operand is not None:
            found |= _partition_columns_in(operand)
    return found


def assert_time_bounded(statement: _SelectAny) -> None:
    """Refuse a statement that reads a partitioned table without pruning it.

    Args:
        statement: any SQLAlchemy select.

    Raises:
        UnboundedScanError: naming the table and the column that must be
            constrained, for every partitioned table the statement touches.
    """
    # get_final_froms() rather than column_descriptions: the latter reports None
    # for an aggregate like select(func.count()).select_from(Alert), and a COUNT
    # over every partition is precisely the unbounded scan this must catch.
    referenced: set[str] = set()
    for entity in statement.get_final_froms():
        name = getattr(entity, "name", None)
        if name in PARTITIONED_TABLES:
            referenced.add(name)

    constrained = _partition_columns_in(statement.whereclause)
    missing = sorted(
        table for table in referenced if f"{table}.{PARTITION_KEYS[table]}" not in constrained
    )
    if missing:
        details = ", ".join(f"{table}.{PARTITION_KEYS[table]}" for table in missing)
        raise UnboundedScanError(
            f"refusing to query {', '.join(missing)} without a time-range predicate "
            f"on {details}. R-34: an unbounded scan of a monthly-partitioned table "
            "reads every partition retention has not dropped. Build the query with "
            "query_partitioned(table, time_range) or add an explicit range on the "
            "partition column."
        )


def query_partitioned(
    table: str,
    time_range: TimeRange,
    *,
    columns: tuple[ColumnElement[object], ...] | None = None,
) -> Select[tuple[object, ...]]:
    """Build a select against a partitioned table, bounded by ``time_range``.

    ``time_range`` is positional so that no call shape omits it. The returned
    statement also passes :func:`assert_time_bounded`, which is checked by a test
    rather than assumed — the two layers must not be allowed to drift apart.

    Args:
        table: a name in :data:`PARTITIONED_TABLES`.
        time_range: the window to prune to.
        columns: what to select; defaults to every column.

    Returns:
        A bounded select.

    Raises:
        ValueError: if ``table`` is not a partitioned table. This function exists
            for the partitioned ones; using it for an ordinary table would hide
            that the caller did not think about which case they were in.
    """
    from app.db import models  # noqa: PLC0415

    if table not in PARTITIONED_TABLES:
        raise ValueError(
            f"{table!r} is not partitioned; query it directly. Routed through "
            "here it would look bounded when it never needed to be."
        )
    if not isinstance(time_range, TimeRange):
        raise TypeError(
            f"expected a TimeRange, got {type(time_range).__name__}. A pair of "
            "timestamps has not been validated, and an unvalidated range cannot "
            "prune partitions reliably."
        )

    entity = getattr(models, _MODEL_FOR_TABLE[table])
    column_key = PARTITION_KEYS[table]
    column = getattr(entity, column_key)
    selected = columns if columns is not None else (entity,)
    statement = select(*selected).where(column >= time_range.start).where(column < time_range.end)
    assert_time_bounded(statement)
    return statement


@dataclass(frozen=True, slots=True)
class AggregateStatements:
    """The four statements a persistent overview aggregation runs (T-416).

    Attributes:
        totals: one row per ``(severity, status, verdict)`` with its count.
        series: one row per ``(bucket, severity)`` with its count.
        entities: one row per ``(entity_id, kind, value, severity)`` with its
            count, its occurrence sum, its open count, its highest score and its
            latest ``last_seen``, biggest first, capped at the requested limit.
        families: one row per ``(family, severity)`` with its count, largest
            first, capped at the requested limit.
    """

    # Each statement selects a different column shape, so the columns are packed:
    # ``Select[Unpack[tuple[Any, ...]]]`` is a select of any arity, which is what
    # this holds. Naming one shape here would make three of the four a lie.
    totals: _SelectAny
    series: _SelectAny
    entities: _SelectAny
    families: _SelectAny


def alert_aggregate_statements(
    time_range: TimeRange,
    *,
    bucket_seconds: int,
    entity_limit: int,
    family_limit: int,
) -> AggregateStatements:
    """Build the four GROUP BY statements behind ``GET /api/v1/overview``.

    The overview's counts must be the *window's* counts -- the client-side version
    this replaces counted pages and said so -- so none of these statements carries
    a row limit except the entity list, and that one is a top-N *of a complete
    grouping*, which is why it can be capped without lying.

    The set is grouped by severity rather than carrying a ``worst_severity``
    expression: the band order lives in :class:`~app.db.models.Severity` (R-38), and
    an adapter folds these rows with the same rank the in-memory path uses rather
    than re-deriving the order in SQL.

    Every statement passes :func:`assert_time_bounded`, and a test asserts that
    dropping the window makes it raise -- R-34 applies to an aggregate exactly as
    it applies to a page.

    Args:
        time_range: the bounded window. Positional, like :func:`query_partitioned`.
        bucket_seconds: the series' resolution in seconds.
        entity_limit: how many entities the top-N keeps.
        family_limit: how many families the mix keeps.

    Returns:
        The four bounded statements.

    Raises:
        ValueError: if the bucket is not positive, or a limit is not.
    """
    from app.db import models  # noqa: PLC0415

    if bucket_seconds < 1:
        msg = "bucket_seconds must be positive"
        raise ValueError(msg)
    if entity_limit < 1:
        msg = "entity_limit must be positive"
        raise ValueError(msg)
    if family_limit < 1:
        msg = "family_limit must be positive"
        raise ValueError(msg)

    def bounded(statement: _Statement) -> _Statement:
        """Attach R-34's window predicate, which every statement below carries.

        Generic in the statement's own type on purpose: ``Select`` carries the
        columns in its parameters, and flattening them to ``tuple[object, ...]``
        would make every caller's type a lie.
        """
        return statement.where(models.Alert.created_at >= time_range.start).where(
            models.Alert.created_at < time_range.end
        )

    totals = bounded(
        select(
            models.Alert.severity,
            models.Alert.status,
            models.Alert.verdict,
            func.count().label("alerts"),
        ).select_from(models.Alert)
    ).group_by(models.Alert.severity, models.Alert.status, models.Alert.verdict)

    # An epoch floor rather than ``date_bin``: the same expression works on any
    # supported server, and the bucket boundary is then the same arithmetic the
    # in-memory path does over ``timedelta``.
    bucket = (
        func.floor(
            func.extract("epoch", models.Alert.created_at - time_range.start) / bucket_seconds
        )
    ).label("bucket")
    series = bounded(
        select(bucket, models.Alert.severity, func.count().label("alerts")).select_from(
            models.Alert
        )
    ).group_by(bucket, models.Alert.severity)

    entities = (
        bounded(
            select(
                models.Alert.entity_id,
                models.Entity.kind,
                models.Entity.value,
                models.Alert.severity,
                func.count().label("alerts"),
                func.sum(models.Alert.occurrence_count).label("occurrences"),
                func.sum(case((models.Alert.status == models.AlertStatus.open, 1), else_=0)).label(
                    "open_alerts"
                ),
                func.max(models.Alert.score).label("max_score"),
                func.max(models.Alert.last_seen).label("last_seen"),
            ).select_from(models.Alert)
            # LEFT JOIN: an entity the registry has never seen still has alerts,
            # and dropping those rows would understate the window. ``kind`` and
            # ``value`` come back NULL and the response says the id is unnamed.
            .join(models.Entity, models.Entity.id == models.Alert.entity_id, isouter=True)
        )
        .group_by(
            models.Alert.entity_id, models.Entity.kind, models.Entity.value, models.Alert.severity
        )
        .order_by(func.count().desc(), models.Alert.entity_id.asc())
        .limit(entity_limit)
    )

    # The mix keeps a blank family as a row: dropping it here would make the
    # bars add up to less than the window, and the client is the place that
    # decides how to label "the model attributed no family".
    families = (
        bounded(
            select(
                models.Alert.family,
                models.Alert.severity,
                func.count().label("alerts"),
            ).select_from(models.Alert)
        )
        .group_by(models.Alert.family, models.Alert.severity)
        .order_by(func.count().desc(), models.Alert.family.asc())
        .limit(family_limit)
    )

    for statement in (totals, series, entities, families):
        assert_time_bounded(statement)
    return AggregateStatements(totals=totals, series=series, entities=entities, families=families)


#: Partitioned table name to the model class that maps it.
_MODEL_FOR_TABLE: dict[str, str] = {"alerts": "Alert", "ingest_stats": "IngestStat"}

__all__ = [
    "MAX_QUERY_SPAN_DAYS",
    "AggregateStatements",
    "TimeRange",
    "UnboundedScanError",
    "alert_aggregate_statements",
    "assert_time_bounded",
    "query_partitioned",
]
