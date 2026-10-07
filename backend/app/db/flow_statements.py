"""The statements behind the flow store's reads (T-418, FR-52).

Kept as pure builders, like :func:`app.db.repository.alert_aggregate_statements` and
:mod:`app.db.log_statements`, so what the store will ask the database can be asserted as
SQL -- text, predicates and parameters -- without a server. The live round trip is in
``tests/test_flow_store_live.py``, which skips unless a PostgreSQL is configured.

Every read is a **time window** (R-34): each builder takes a validated
:class:`~app.db.repository.TimeRange`, adds both bounds, and passes
:func:`~app.db.repository.assert_time_bounded`. ``flow_events`` is not partitioned
today, so that inspector is a no-op for it -- called deliberately, because the day it is
partitioned these are already the statements the rule demands.

Three shapes, one per question design.md §4.4 asks, and **no alert join in any of
them**: a ``flow@1`` record carries no score, severity or entity, so the score overlay
and the per-address alert counts are composed at the endpoint from the alert store,
which is the side of the system that owns those numbers (D-075's rule: the endpoint
joins, the read model counts its own traffic).

* :func:`bucket_rows_statement` -- flow, byte and packet totals per bucket. The bucket
  is ``date_bin``: PostgreSQL 16 is the deployed server, and ``date_bin`` takes the
  width as a parameter, which ``date_trunc`` cannot do for an arbitrary number of
  minutes. It lands on the same grid :func:`app.services.flow_read_model.bucket_index`
  computes, so a stored read and a rolled-up read agree bucket for bucket.
* :func:`node_rows_statement` -- per-address totals, busiest first, capped. Both ends
  count: an address that only ever receives is half the traffic a graph is drawn from.
* :func:`edge_rows_statement` -- per-directional-pair totals, heaviest first, capped.

No statement here writes, and none of them is called on a request path that has no
store: :mod:`app.services.flow_store` is the only caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Integer, Interval, func, literal, select
from sqlalchemy.sql.elements import Label

from app.db.models import FlowEvent
from app.db.repository import SelectAny, TimeRange, assert_time_bounded

__all__ = [
    "BucketRows",
    "EdgeRows",
    "NodeRows",
    "bucket_rows_statement",
    "coverage_statement",
    "edge_rows_statement",
    "node_rows_statement",
]


def _bounded(
    statement: SelectAny,
    time_range: TimeRange,
    *,
    protocol: str | None = None,
    direction: str | None = None,
) -> SelectAny:
    """Apply the window and the two filters every read here shares, then check it."""
    statement = statement.where(FlowEvent.timestamp >= time_range.start).where(
        FlowEvent.timestamp < time_range.end
    )
    if protocol is not None:
        statement = statement.where(FlowEvent.protocol == protocol)
    if direction is not None:
        statement = statement.where(FlowEvent.direction == direction)
    assert_time_bounded(statement)
    return statement


def _bin_expression(time_range: TimeRange, bucket_minutes: int) -> Label[datetime]:
    """The bucket each record belongs to, as a timestamp ``date_bin`` computes.

    Returns:
        A labelled expression: ``date_bin(width, timestamp, window_start)``.

    Raises:
        ValueError: if ``bucket_minutes`` is not positive -- checked here rather than
            left to PostgreSQL, where a zero-width interval is a server error a caller
            cannot read.
    """
    if bucket_minutes < 1:
        msg = f"bucket_minutes must be positive, got {bucket_minutes}"
        raise ValueError(msg)
    width = literal(timedelta(minutes=bucket_minutes), Interval)
    origin = literal(time_range.start, FlowEvent.timestamp.type)
    return func.date_bin(width, FlowEvent.timestamp, origin).label("start")


@dataclass(frozen=True, slots=True)
class BucketRows:
    """One bucket of the volume series, as the store maps it.

    Attributes:
        start: the bucket's inclusive lower bound, as the database computed it.
        flows: flow records in the bucket.
        bytes: the bytes they carried.
        packets: the packets they carried.
    """

    start: datetime
    flows: int
    bytes: int
    packets: int


@dataclass(frozen=True, slots=True)
class NodeRows:
    """One address's share of the window, as the store maps it.

    Attributes:
        ip: the address.
        flows: records in which it was an end.
        bytes: the bytes those records carried.
        packets: the packets they carried.
        inbound: records in which it was the destination.
        outbound: records in which it was the source.
        first_seen: the oldest record it appeared in.
        last_seen: the newest.
    """

    ip: str
    flows: int
    bytes: int
    packets: int
    inbound: int
    outbound: int
    first_seen: datetime | None
    last_seen: datetime | None


@dataclass(frozen=True, slots=True)
class EdgeRows:
    """One relationship's share of the window, as the store maps it.

    Attributes:
        source: the source address.
        target: the destination address.
        flows: records between them, in that direction.
        bytes: the bytes those records carried.
    """

    source: str
    target: str
    flows: int
    bytes: int


def coverage_statement() -> SelectAny:
    """What the table holds at all: oldest, newest and how many rows.

    Deliberately unwindowed, and the only statement here that is: it answers "has
    anything ever been stored?", which is the question that separates an empty window
    from an empty store -- the distinction the caveats are built on (R-70).
    """
    return select(
        func.min(FlowEvent.timestamp).label("oldest"),
        func.max(FlowEvent.timestamp).label("newest"),
        func.count().label("held"),
    )


def bucket_rows_statement(
    time_range: TimeRange,
    *,
    bucket_minutes: int,
    protocol: str | None = None,
    direction: str | None = None,
) -> SelectAny:
    """Flow, byte and packet totals per bucket, oldest first.

    Only buckets that hold traffic come back; the caller fills the gaps with zeroes, so
    a quiet interval is drawn as an empty bucket rather than silently closed up.
    """
    bucket = _bin_expression(time_range, bucket_minutes)
    statement = (
        select(
            bucket,
            func.count().label("flows"),
            func.coalesce(func.sum(FlowEvent.bytes), 0).label("bytes"),
            func.coalesce(func.sum(FlowEvent.packets), 0).label("packets"),
        )
        .select_from(FlowEvent)
        .group_by(bucket)
        .order_by(bucket)
    )
    return _bounded(statement, time_range, protocol=protocol, direction=direction)


def node_rows_statement(
    time_range: TimeRange,
    *,
    protocol: str | None = None,
    direction: str | None = None,
    limit: int,
) -> SelectAny:
    """Per-address totals, busiest first, capped at ``limit``.

    An address is an *end* of a record, so the source side and the destination side are
    unioned before grouping: one that only ever receives would otherwise be invisible,
    and a graph drawn from senders alone is half the traffic. ``inbound``/``outbound``
    say which end it was, so the two are still distinguishable on the screen.

    Raises:
        ValueError: if ``limit`` is not positive.
    """
    if limit < 1:
        msg = f"limit must be at least 1, got {limit}"
        raise ValueError(msg)
    source_side = _bounded(
        select(
            FlowEvent.src_ip.label("ip"),
            FlowEvent.timestamp.label("timestamp"),
            FlowEvent.bytes.label("bytes"),
            FlowEvent.packets.label("packets"),
            literal(0, Integer).label("inbound"),
            literal(1, Integer).label("outbound"),
        ).select_from(FlowEvent),
        time_range,
        protocol=protocol,
        direction=direction,
    )
    destination_side = _bounded(
        select(
            FlowEvent.dst_ip.label("ip"),
            FlowEvent.timestamp.label("timestamp"),
            FlowEvent.bytes.label("bytes"),
            FlowEvent.packets.label("packets"),
            literal(1, Integer).label("inbound"),
            literal(0, Integer).label("outbound"),
        ).select_from(FlowEvent),
        time_range,
        protocol=protocol,
        direction=direction,
    )
    endpoint = source_side.union_all(destination_side).subquery()
    statement = (
        select(
            endpoint.c.ip.label("ip"),
            func.count().label("flows"),
            func.coalesce(func.sum(endpoint.c.bytes), 0).label("bytes"),
            func.coalesce(func.sum(endpoint.c.packets), 0).label("packets"),
            func.coalesce(func.sum(endpoint.c.inbound), 0).label("inbound"),
            func.coalesce(func.sum(endpoint.c.outbound), 0).label("outbound"),
            func.min(endpoint.c.timestamp).label("first_seen"),
            func.max(endpoint.c.timestamp).label("last_seen"),
        )
        .select_from(endpoint)
        .group_by(endpoint.c.ip)
        # Busiest first, and a tie broken by bytes then address -- the order the
        # in-process rollup sorts by (``-flows, -bytes, ip``), so the same window lists
        # the same addresses in the same order whichever source answered.
        .order_by(
            func.count().desc(),
            func.coalesce(func.sum(endpoint.c.bytes), 0).desc(),
            endpoint.c.ip.asc(),
        )
        .limit(limit)
    )
    assert_time_bounded(statement)
    return statement


def edge_rows_statement(
    time_range: TimeRange,
    *,
    protocol: str | None = None,
    direction: str | None = None,
    limit: int,
) -> SelectAny:
    """Per-pair totals, heaviest first, capped at ``limit``.

    Directional: ``a -> b`` and ``b -> a`` are two rows, because a count that merged
    them would describe a conversation between peers, and the responder reads an edge
    to find out which way the data went.

    Raises:
        ValueError: if ``limit`` is not positive.
    """
    if limit < 1:
        msg = f"limit must be at least 1, got {limit}"
        raise ValueError(msg)
    statement = (
        select(
            FlowEvent.src_ip.label("source"),
            FlowEvent.dst_ip.label("target"),
            func.count().label("flows"),
            func.coalesce(func.sum(FlowEvent.bytes), 0).label("bytes"),
        )
        .select_from(FlowEvent)
        .group_by(FlowEvent.src_ip, FlowEvent.dst_ip)
        # The rollup's tie-break order too: relationships equal in count are ordered by
        # the traffic they carried, then by the pair.
        .order_by(
            func.count().desc(),
            func.coalesce(func.sum(FlowEvent.bytes), 0).desc(),
            FlowEvent.src_ip.asc(),
            FlowEvent.dst_ip.asc(),
        )
        .limit(limit)
    )
    return _bounded(statement, time_range, protocol=protocol, direction=direction)
