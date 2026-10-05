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

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.sql.elements import BinaryExpression

from app.db.models import PARTITION_KEYS, PARTITIONED_TABLES

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


def assert_time_bounded(statement: Select[tuple[object, ...]]) -> None:
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


#: Partitioned table name to the model class that maps it.
_MODEL_FOR_TABLE: dict[str, str] = {"alerts": "Alert", "ingest_stats": "IngestStat"}

__all__ = [
    "MAX_QUERY_SPAN_DAYS",
    "TimeRange",
    "UnboundedScanError",
    "assert_time_bounded",
    "query_partitioned",
]
