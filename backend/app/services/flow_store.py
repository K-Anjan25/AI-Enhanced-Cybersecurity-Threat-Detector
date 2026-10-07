"""The flow read model's persistent half: ``flow_events`` (T-418, FR-52).

The traffic explorer's traffic comes from here when a deployment names a database:
records are written on ingest and the three panels are grouped in SQL, so a read is not
bounded by one process's memory and survives a restart. When no database is named the
rollup answers instead -- :mod:`app.services.flow_read_model` -- and the endpoint says
which of the two it is, because "this window is the whole window" and "this window is
whatever minutes the rollup still holds" are different claims about one screen.

**The write is one statement per batch.** A partially stored batch would leave a window
that is half-present, and every count on the screen would then be a count of something
the collector did not send in that shape. ``bytes`` is ``src_bytes + dst_bytes`` summed
once here, so no grouping query adds two columns and the addition has one definition.

**A cap never truncates a count.** The totals come from the *series* -- every bucket's
flows summed -- and the entity and edge counts come from their own ``count(distinct)``
queries, so ``nodes`` is the window's number whatever the listed top-N was. That is
T-416's rule, applied to traffic.

**Failure is one exception.** Every ``SQLAlchemyError`` a read or write hits becomes
:class:`FlowStoreUnavailable`, which the routes turn into a 503 the client can retry,
rather than a 500 that says nothing about whether the data is intact or an empty screen
that says the window held nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.flow_statements import (
    bucket_rows_statement,
    coverage_statement,
    edge_rows_statement,
    node_rows_statement,
)
from app.db.models import FlowEvent
from app.db.repository import MAX_QUERY_SPAN_DAYS, SelectAny, TimeRange
from app.schemas.ingest import FlowRecordIn
from app.services.flow_read_model import (
    DEFAULT_FLOW_BUCKET_MINUTES,
    DEFAULT_FLOW_EDGE_LIMIT,
    DEFAULT_FLOW_ENTITY_LIMIT,
    FlowAggregate,
    FlowBucket,
    FlowEdge,
    FlowFilters,
    FlowNode,
    FlowTotals,
    FlowWindow,
    bucket_starts,
)

__all__ = ["FlowCoverage", "FlowStoreUnavailable", "PostgresFlowStore"]


class FlowStoreUnavailable(RuntimeError):
    """The store could not answer: no connection, no table, or a refused statement.

    Raised for every ``SQLAlchemyError`` a read or write hits, so the routes have one
    exception to catch and the client gets a 503 it can retry.
    """


@dataclass(frozen=True, slots=True)
class FlowCoverage:
    """What the table holds at all.

    Attributes:
        oldest: the oldest stored instant, or ``None`` when the table is empty.
        newest: the newest stored instant, or ``None`` when the table is empty.
        held: how many rows the table holds.
    """

    oldest: datetime | None
    newest: datetime | None
    held: int

    @property
    def empty(self) -> bool:
        """Whether nothing has ever been stored."""
        return self.held == 0


class PostgresFlowStore:
    """The flow read model, backed by the ``flow_events`` table.

    ``coverage_ttl_seconds`` memoises the "what does the table hold" query the caveats
    need: it is a whole-table aggregate, and asking it once per read of a live screen
    would make the cheapest question here the most expensive one. The cache is dropped
    by :meth:`append`, so a read after a write never describes the state before it.
    """

    __slots__ = ("_coverage", "_coverage_at", "_coverage_ttl", "_sessions")

    #: What the response's ``source`` field carries (T-419's convention).
    name = "store"

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        coverage_ttl_seconds: float = 30.0,
    ) -> None:
        """Bind the store to a session factory.

        Raises:
            ValueError: if the TTL is not positive, so a zero TTL cannot mean
                "cache forever" by accident.
        """
        if coverage_ttl_seconds <= 0:
            msg = f"coverage_ttl_seconds must be positive, got {coverage_ttl_seconds}"
            raise ValueError(msg)
        self._sessions = sessions
        self._coverage_ttl = coverage_ttl_seconds
        self._coverage: FlowCoverage | None = None
        self._coverage_at: datetime | None = None

    @property
    def max_span_seconds(self) -> float:
        """Widest window the store will answer: R-34's own ceiling."""
        return MAX_QUERY_SPAN_DAYS * 86_400.0

    async def append(self, records: Sequence[FlowRecordIn]) -> int:
        """Store a batch of accepted records in one transaction, returning how many."""
        if not records:
            return 0
        rows = [
            {
                "timestamp": record.timestamp,
                "src_ip": str(record.src_ip),
                "dst_ip": str(record.dst_ip),
                "protocol": record.protocol.value,
                "direction": record.direction.value,
                "bytes": record.src_bytes + record.dst_bytes,
                "packets": record.packets,
            }
            for record in records
        ]
        async with self._sessions() as session:
            try:
                async with session.begin():
                    await session.execute(insert(FlowEvent), rows)
            except SQLAlchemyError as exc:
                msg = f"the flow store could not accept a batch: {exc}"
                raise FlowStoreUnavailable(msg) from exc
        # A write makes the store's description of itself stale; drop it now rather
        # than serving a coverage that predates the batch just stored.
        self._coverage = None
        self._coverage_at = None
        return len(rows)

    async def coverage(self, *, refresh: bool = False) -> FlowCoverage:
        """What the table holds, from a cached answer while it is still fresh."""
        if not refresh and self._coverage is not None and self._fresh():
            return self._coverage
        rows = await self._all(coverage_statement())
        row = rows[0] if rows else None
        coverage = FlowCoverage(
            oldest=_as_datetime(getattr(row, "oldest", None)),
            newest=_as_datetime(getattr(row, "newest", None)),
            held=int(getattr(row, "held", 0) or 0) if row is not None else 0,
        )
        self._coverage = coverage
        self._coverage_at = datetime.now(UTC)
        return coverage

    async def summary(
        self,
        window: FlowWindow,
        *,
        bucket_minutes: int = DEFAULT_FLOW_BUCKET_MINUTES,
        entity_limit: int = DEFAULT_FLOW_ENTITY_LIMIT,
        edge_limit: int = DEFAULT_FLOW_EDGE_LIMIT,
        filters: FlowFilters | None = None,
    ) -> FlowAggregate:
        """Aggregate the window in SQL: one statement per panel, and two counts.

        The series is materialised at every bucket the window tiles, empty ones
        included, so a quiet interval is a zero rather than a closed-up gap -- the same
        shape the rollup produces, which is what lets one screen draw either source.

        Raises:
            FlowStoreUnavailable: if the database refused any of the statements.
        """
        chosen = filters or FlowFilters()
        span = TimeRange(start=window.start, end=window.end)
        series = await self._series(span, bucket_minutes=bucket_minutes, filters=chosen)
        nodes = await self._nodes(span, limit=entity_limit, filters=chosen)
        edges = await self._edges(span, limit=edge_limit, filters=chosen)
        node_count = await self._count(span, filters=chosen, shape="nodes")
        edge_count = await self._count(span, filters=chosen, shape="edges")
        return FlowAggregate(
            series=series,
            entities=nodes,
            edges=edges,
            totals=FlowTotals(
                # From the series, not from the capped lists: a count that came from a
                # top-N would move when the cap did (T-416's defect, on traffic).
                flows=sum(point.flows for point in series),
                bytes=sum(point.bytes for point in series),
                packets=sum(point.packets for point in series),
                nodes=node_count,
                edges=edge_count,
                nodes_capped=node_count > len(nodes),
                edges_capped=edge_count > len(edges),
                # A store keeps every record it is given, so nothing here is untracked.
                untracked_address_flows=0,
                untracked_pair_flows=0,
            ),
        )

    def _fresh(self) -> bool:
        """Whether the cached coverage is still inside its TTL."""
        if self._coverage_at is None:
            return False
        return (datetime.now(UTC) - self._coverage_at).total_seconds() < self._coverage_ttl

    async def _all(self, statement: SelectAny) -> list[Any]:
        """Run one statement, translating a driver failure into the store's refusal.

        ``SelectAny`` and ``list[Any]`` rather than a shape per caller: the store reads
        rows by column name in four places and by position in one, and a signature that
        claimed to know which would have to be wrong for one of them.
        """
        async with self._sessions() as session:
            try:
                return list((await session.execute(statement)).all())
            except SQLAlchemyError as exc:
                msg = f"the flow store could not answer: {exc}"
                raise FlowStoreUnavailable(msg) from exc

    async def _series(
        self, span: TimeRange, *, bucket_minutes: int, filters: FlowFilters
    ) -> list[FlowBucket]:
        """The volume series, with the empty buckets materialised."""
        rows = await self._all(
            bucket_rows_statement(
                span,
                bucket_minutes=bucket_minutes,
                protocol=filters.protocol,
                direction=filters.direction,
            )
        )
        found = {
            _as_datetime(getattr(row, "start", None)): (
                int(getattr(row, "flows", 0) or 0),
                int(getattr(row, "bytes", 0) or 0),
                int(getattr(row, "packets", 0) or 0),
            )
            for row in rows
        }
        series: list[FlowBucket] = []
        for start in bucket_starts(span.start, span.end, bucket_minutes):
            flows, total, packets = found.get(start, (0, 0, 0))
            series.append(FlowBucket(start=start, flows=flows, bytes=total, packets=packets))
        return series

    async def _nodes(self, span: TimeRange, *, limit: int, filters: FlowFilters) -> list[FlowNode]:
        """The busiest addresses, capped."""
        rows = await self._all(
            node_rows_statement(
                span, protocol=filters.protocol, direction=filters.direction, limit=limit
            )
        )
        return [
            FlowNode(
                ip=str(getattr(row, "ip", "")),
                flows=int(getattr(row, "flows", 0) or 0),
                bytes=int(getattr(row, "bytes", 0) or 0),
                packets=int(getattr(row, "packets", 0) or 0),
                inbound=int(getattr(row, "inbound", 0) or 0),
                outbound=int(getattr(row, "outbound", 0) or 0),
                first_seen=_as_datetime(getattr(row, "first_seen", None)),
                last_seen=_as_datetime(getattr(row, "last_seen", None)),
            )
            for row in rows
        ]

    async def _edges(self, span: TimeRange, *, limit: int, filters: FlowFilters) -> list[FlowEdge]:
        """The heaviest relationships, capped."""
        rows = await self._all(
            edge_rows_statement(
                span, protocol=filters.protocol, direction=filters.direction, limit=limit
            )
        )
        return [
            FlowEdge(
                source=str(getattr(row, "source", "")),
                target=str(getattr(row, "target", "")),
                flows=int(getattr(row, "flows", 0) or 0),
                bytes=int(getattr(row, "bytes", 0) or 0),
            )
            for row in rows
        ]

    async def _count(self, span: TimeRange, *, filters: FlowFilters, shape: str) -> int:
        """How many distinct addresses or pairs the **whole** window holds.

        Counted separately from the capped lists because the answer must be independent
        of the cap: ``nodes_capped`` is a statement about this number, and a client
        inferring it from a top-N could only ever say "there may be more".
        """
        left: SelectAny
        right: SelectAny
        if shape == "nodes":
            left = select(FlowEvent.src_ip.label("value"))
            right = select(FlowEvent.dst_ip.label("value"))
        else:
            left = select(FlowEvent.src_ip.label("source"), FlowEvent.dst_ip.label("target"))
            right = select(FlowEvent.src_ip.label("source"), FlowEvent.dst_ip.label("target"))
        parts = []
        for side in (left, right):
            bounded = side.where(FlowEvent.timestamp >= span.start).where(
                FlowEvent.timestamp < span.end
            )
            if filters.protocol is not None:
                bounded = bounded.where(FlowEvent.protocol == filters.protocol)
            if filters.direction is not None:
                bounded = bounded.where(FlowEvent.direction == filters.direction)
            parts.append(bounded)
        distinct = parts[0].union(parts[1]).subquery()
        statement: SelectAny = select(func.count()).select_from(distinct)
        rows = await self._all(statement)
        return int(rows[0][0]) if rows else 0


def _as_datetime(value: object) -> datetime | None:
    """A row's timestamp as a datetime, or ``None`` when it is not one."""
    return value if isinstance(value, datetime) else None
