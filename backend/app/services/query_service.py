"""Alert queries: filters that combine, and pagination that does not drift.

Two properties this module exists to guarantee:

**R-34 is not optional.** Every query goes through :func:`query_partitioned`,
whose ``time_range`` parameter is positional. There is no call shape that
reaches the partitioned ``alerts`` table without a bounded window, so "remember
the predicate" is not a discipline note.

**Pagination is stable under concurrent inserts.** Ordering and the cursor both
use ``(created_at, id)``. Per D-030 ``id`` is not unique across partitions, so a
cursor keyed on ``id`` alone would tie, and a keyset cursor with ties either
skips or repeats rows. Offset pagination is not used at all: it is unstable by
construction, since an insert earlier in the ordering shifts every later page.

The cursor comparison is a row-value comparison rather than two separate
predicates. ``(created_at, id) < (a, b)`` is not the same as
``created_at < a AND id < b``, and the second silently drops rows that share a
timestamp with the cursor row.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.models import Alert
from app.db.repository import TimeRange, query_partitioned
from app.schemas.query import (
    AlertPage,
    AlertQuery,
    AlertRow,
    decode_cursor,
    encode_cursor,
)

__all__ = ["build_alert_select", "paginate", "time_range_of"]


def time_range_of(query: AlertQuery) -> TimeRange:
    """The validated range, so callers cannot re-derive an unvalidated one."""
    return TimeRange(start=query.start, end=query.end)


def build_alert_select(query: AlertQuery) -> sa.Select[tuple[object, ...]]:
    """Build the bounded, filtered, ordered select for one page.

    Raises:
        ValueError: if the time range is not usable. Propagated from TimeRange.
        CursorError: if a cursor is present and malformed.
    """
    statement = query_partitioned("alerts", time_range_of(query))

    # Filters combine with AND. Each is applied only when supplied, so an
    # omitted filter narrows nothing rather than narrowing to empty.
    if query.severity:
        statement = statement.where(Alert.severity.in_(sorted(query.severity)))
    if query.status:
        statement = statement.where(Alert.status.in_(sorted(query.status)))
    if query.family:
        statement = statement.where(Alert.family.in_(sorted(query.family)))
    if query.entity_id is not None:
        statement = statement.where(Alert.entity_id == query.entity_id)
    if query.min_score is not None:
        statement = statement.where(Alert.score >= query.min_score)

    if query.cursor is not None:
        created_at, row_id = decode_cursor(query.cursor)
        key = sa.tuple_(Alert.created_at, Alert.id)
        bound = sa.tuple_(sa.literal(created_at), sa.literal(row_id))
        # Row-value comparison: strictly "after" the cursor in sort order.
        statement = statement.where(key < bound if query.order == "desc" else key > bound)

    # One extra row is fetched so the presence of a next page is known without a
    # second COUNT, which on a partitioned table would scan again.
    # Both key columns, not just created_at: rows sharing a timestamp must still
    # have a total order, or the keyset cursor cannot tell them apart.
    ordering = (
        (Alert.created_at.desc(), Alert.id.desc())
        if query.order == "desc"
        else (Alert.created_at.asc(), Alert.id.asc())
    )
    return statement.order_by(*ordering).limit(query.limit + 1)


def _trace_id_of(row: Alert) -> str | None:
    """The trace id recorded for an alert row, if it has one.

    It lives inside ``window_ref`` -- the pointer to the window the case opened
    on -- rather than in a column of its own: the trace is part of that window's
    provenance, and ``window_ref`` is specified as opaque JSONB for exactly this
    kind of bounded addition. Anything that is not the shape this wrote is
    reported as absent rather than guessed at.
    """
    window_ref = row.window_ref
    if not isinstance(window_ref, dict):
        return None
    trace_id = window_ref.get("trace_id")
    return trace_id if isinstance(trace_id, str) and trace_id else None


def paginate(rows: list[Alert], query: AlertQuery) -> AlertPage:
    """Turn fetched rows into a page, setting a cursor only if there is more."""
    has_more = len(rows) > query.limit
    page_rows = rows[: query.limit]
    next_cursor = (
        encode_cursor(page_rows[-1].created_at, page_rows[-1].id)
        if has_more and page_rows
        else None
    )
    return AlertPage(
        items=[
            AlertRow(
                id=row.id,
                created_at=row.created_at,
                entity_id=row.entity_id,
                family=row.family,
                severity=row.severity,
                score=row.score,
                status=row.status,
                first_seen=row.first_seen,
                last_seen=row.last_seen,
                occurrence_count=row.occurrence_count,
                trace_id=_trace_id_of(row),
            )
            for row in page_rows
        ],
        next_cursor=next_cursor,
        limit=query.limit,
        order=query.order,
    )
