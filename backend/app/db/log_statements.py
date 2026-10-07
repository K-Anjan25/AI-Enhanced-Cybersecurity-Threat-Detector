"""The statements behind the log store's reads (T-419).

Kept as pure builders, like :func:`app.db.repository.alert_aggregate_statements`, so
what the store will ask the database can be asserted as SQL -- text, parameters and
predicates -- without a server. The live round trip is in
``tests/test_log_store_live.py``, which skips unless a PostgreSQL is configured.

Every read here is a **time window** (R-34): each builder takes a validated
:class:`~app.db.repository.TimeRange` and adds both bounds, and each passes
:func:`~app.db.repository.assert_time_bounded` before it is returned. ``log_events``
is not partitioned today, so that inspector is a no-op for it -- deliberately called
anyway, because the day it is partitioned these statements are already the ones the
rule demands, and a statement assembled without a window would fail here rather than
in production.

**The cluster key is a column, not an expression.** ``log_events.key`` is written
when a line is accepted, by ``app.services.log_keys.cluster_key`` -- the same
function the live tail folds by. Grouping on the stored column means the fold has
one definition, "the lines behind this cluster" is an indexed equality, and a stored
read cannot invent a cluster the tail would not have shown.

Three shapes, one per question a screen asks:

* :func:`cluster_rows_statement` -- one row per cluster in the window, biggest first,
  capped: the fold design.md §4.5 promises.
* :func:`cluster_levels_statement` -- how many lines of each level a cluster holds,
  restricted to the keys the first statement returned, so its cost is bounded by the
  read's own row limit rather than by the window.
* :func:`line_rows_statement` and :func:`window_line_count_statement` -- the raw
  lines behind one cluster (or one window), newest ``limit`` kept and returned
  oldest-first, with the count of what matched before that cap.

Two counting statements exist only to make a screen honest rather than empty:
:func:`distinct_cluster_count_statement` is what lets a read say "30 clusters, the
first 10 shown", and :func:`untemplated_line_count_statement` is what lets it say
that some lines are grouped by a digest because the collector mined no template for
them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from app.db.models import LogEvent
from app.db.repository import SelectAny, TimeRange, assert_time_bounded
from app.schemas.ingest import LogLevel

__all__ = [
    "ClusterRows",
    "cluster_levels_statement",
    "cluster_rows_statement",
    "coverage_statement",
    "distinct_cluster_count_statement",
    "line_rows_statement",
    "untemplated_line_count_statement",
    "window_line_count_statement",
]

#: The newest line's message and parameters are picked with an ordered array
#: aggregate rather than a window function: one pass, no ranking to get wrong, and
#: ``[1]`` on an array that is ordered newest-first is the newest element by
#: construction. Ties break on ``id``, which is arrival order, matching the tail's
#: rule that a later line at the same instant becomes the sample.
_NEWEST_FIRST = (LogEvent.timestamp.desc(), LogEvent.id.desc())


def _bounded(
    statement: SelectAny,
    time_range: TimeRange,
    *,
    host: str | None,
    service: str | None,
    level: LogLevel | None,
    key: str | None = None,
) -> SelectAny:
    """Attach the window and the shared filters, then check R-34's predicate is there.

    Both ends are always added: a one-sided bound still reads everything after it.
    The filters are ``None``-able because the API's are optional, and ``None`` means
    "no filter" rather than "match the empty string".
    """
    statement = statement.where(LogEvent.timestamp >= time_range.start).where(
        LogEvent.timestamp < time_range.end
    )
    if host is not None:
        statement = statement.where(LogEvent.host == host)
    if service is not None:
        statement = statement.where(LogEvent.service == service)
    if level is not None:
        statement = statement.where(LogEvent.level == level.value)
    if key is not None:
        statement = statement.where(LogEvent.key == key)
    assert_time_bounded(statement)
    return statement


@dataclass(frozen=True, slots=True)
class ClusterRows:
    """One aggregate row of the fold, as the store maps it.

    Attributes:
        key: the cluster key: a template id, or ``message:<digest>``.
        lines: how many lines in the window folded into it.
        first_seen: the oldest line's instant.
        last_seen: the newest line's instant.
        sample_message: the newest line's message.
        sample_parameters: the newest line's parameters.
        hosts: the distinct hosts that emitted it, unsorted as the database returned
            them -- the caller sorts, so the order on the wire is the caller's.
        services: likewise, for services.
    """

    key: str
    lines: int
    first_seen: datetime
    last_seen: datetime
    sample_message: str
    sample_parameters: dict[str, object]
    hosts: list[str]
    services: list[str]


def cluster_rows_statement(
    time_range: TimeRange,
    *,
    host: str | None = None,
    service: str | None = None,
    level: LogLevel | None = None,
    limit: int,
) -> SelectAny:
    """One row per cluster in the window, busiest first, capped at ``limit``.

    Ordering is ``count DESC, key ASC``: the tail's own order, so the same window
    read from the store and from a tail lists clusters the same way. The cap is a
    top-N *of a complete grouping*, which is why it does not make the counts a lie --
    the row says how many lines it folded, and the read separately reports how many
    clusters there were.

    Raises:
        ValueError: if ``limit`` is not positive.
    """
    if limit < 1:
        msg = f"limit must be at least 1, got {limit}"
        raise ValueError(msg)
    labelled = LogEvent.key.label("key")
    statement = _bounded(
        select(
            labelled,
            func.count().label("lines"),
            func.min(LogEvent.timestamp).label("first_seen"),
            func.max(LogEvent.timestamp).label("last_seen"),
            func.array_agg(aggregate_order_by(LogEvent.message, *_NEWEST_FIRST))[1].label(
                "sample_message"
            ),
            func.array_agg(aggregate_order_by(LogEvent.parameters, *_NEWEST_FIRST))[1].label(
                "sample_parameters"
            ),
            func.array_agg(func.distinct(LogEvent.host)).label("hosts"),
            func.array_agg(func.distinct(LogEvent.service)).label("services"),
        ).select_from(LogEvent),
        time_range,
        host=host,
        service=service,
        level=level,
    )
    return statement.group_by(labelled).order_by(func.count().desc(), labelled.asc()).limit(limit)


def cluster_levels_statement(
    time_range: TimeRange,
    *,
    keys: list[str],
    host: str | None = None,
    service: str | None = None,
    level: LogLevel | None = None,
) -> SelectAny:
    """``(key, level, count)`` for the given keys inside the window.

    Scoped to the keys the fold returned, so the work is bounded by the read's row
    limit rather than by the window's cardinality, and scoped to the window and
    filters for the same reason the fold is: a level histogram that included lines
    the fold excluded would describe a different set of lines than the row it
    annotates.

    Raises:
        ValueError: if ``keys`` is empty. An ``IN ()`` that matches nothing would be
            a query per read that can never return a row.
    """
    if not keys:
        msg = "keys must not be empty; there is nothing to count levels for"
        raise ValueError(msg)
    statement = _bounded(
        select(
            LogEvent.key.label("key"),
            LogEvent.level.label("level"),
            func.count().label("lines"),
        ).select_from(LogEvent),
        time_range,
        host=host,
        service=service,
        level=level,
    )
    return statement.where(LogEvent.key.in_(keys)).group_by(LogEvent.key, LogEvent.level)


def distinct_cluster_count_statement(
    time_range: TimeRange,
    *,
    host: str | None = None,
    service: str | None = None,
    level: LogLevel | None = None,
) -> SelectAny:
    """How many distinct clusters the window holds, before any row limit."""
    statement = _bounded(
        select(func.count(func.distinct(LogEvent.key)).label("clusters")).select_from(LogEvent),
        time_range,
        host=host,
        service=service,
        level=level,
    )
    return statement


def window_line_count_statement(
    time_range: TimeRange,
    *,
    host: str | None = None,
    service: str | None = None,
    level: LogLevel | None = None,
    key: str | None = None,
) -> SelectAny:
    """How many lines the window holds under these filters, before any row limit.

    Called twice with different arguments and for different reasons: with the read's
    filters it is ``lines_seen``, and without them (``present``) it is what
    distinguishes "nothing was stored in this window" from "the filter removed
    everything" -- two empty screens an analyst acts on differently (R-70).
    """
    return _bounded(
        select(func.count().label("lines")).select_from(LogEvent),
        time_range,
        host=host,
        service=service,
        level=level,
        key=key,
    )


def untemplated_line_count_statement(
    time_range: TimeRange,
    *,
    host: str | None = None,
    service: str | None = None,
    level: LogLevel | None = None,
    key: str | None = None,
) -> SelectAny:
    """How many matching lines carried no template id, so folded by message digest.

    ``template_id IS NULL`` rather than a prefix test on ``key``: a collector could
    legitimately send a template id that begins ``message:``, and reading that as a
    digest would misreport which lines had a mined template.
    """
    statement = _bounded(
        select(func.count().label("lines")).select_from(LogEvent),
        time_range,
        host=host,
        service=service,
        level=level,
        key=key,
    )
    return statement.where(LogEvent.template_id.is_(None))


def line_rows_statement(
    time_range: TimeRange,
    *,
    host: str | None = None,
    service: str | None = None,
    level: LogLevel | None = None,
    key: str | None = None,
    limit: int,
) -> SelectAny:
    """The newest ``limit`` matching lines, newest first.

    Newest first *in SQL* and reversed by the caller, which is the same thing the
    tail does in one step: ``ORDER BY timestamp DESC LIMIT n`` then reverse. The
    alternative -- ordering ascending and taking the last n -- needs the count, and
    a read that already knows the count can say exactly what it dropped.

    Raises:
        ValueError: if ``limit`` is not positive.
    """
    if limit < 1:
        msg = f"limit must be at least 1, got {limit}"
        raise ValueError(msg)
    statement = _bounded(
        select(
            LogEvent.timestamp,
            LogEvent.host,
            LogEvent.service,
            LogEvent.level,
            LogEvent.message,
            LogEvent.template_id,
            LogEvent.parameters,
            LogEvent.key,
        ).select_from(LogEvent),
        time_range,
        host=host,
        service=service,
        level=level,
        key=key,
    )
    return statement.order_by(*_NEWEST_FIRST).limit(limit)


def coverage_statement() -> SelectAny:
    """The oldest and newest instant the store holds, and how many lines it holds.

    Deliberately **not** windowed: the question "how far back does this store reach"
    is about the store, and a coverage that was itself bounded would answer a
    different one. This is the single statement here that reads outside a range, and
    it reads only ``min``/``max`` of an indexed column plus a count, which is why it
    is cached by the caller rather than run per read.
    """
    return select(
        func.min(LogEvent.timestamp).label("oldest"),
        func.max(LogEvent.timestamp).label("newest"),
        func.count().label("lines"),
    ).select_from(LogEvent)
