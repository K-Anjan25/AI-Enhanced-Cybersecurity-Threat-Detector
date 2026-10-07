"""The traffic read model's arithmetic and its in-process half (T-418, FR-52).

design.md §4.4 draws the traffic explorer from three numbers: a brushable series of
**flow volume**, an entity table, and a force-directed graph whose **edges are flow
counts**. Until this module existed the screen got all three from the alert API: the
"volume" was the raw-record count the alerts carried, and an edge meant two entities
appeared in one correlation trace. Every figure on the screen was therefore a statement
about the *alerted* subset of the traffic, and the panel said so.

**What a flow read model counts, and what it must not pretend to.** A ``flow@1`` record
says when a conversation happened, between which two addresses, how much it moved and in
which direction. It says nothing about entities, severity or scores: those are the alert
side of the system, and the endpoint joins them onto the addresses by the one key the
two sides share -- an alert's entity value *is* the source address for flow-modality
detections (``app.pipeline``'s sink keys a flow window by ``str(flow.src_ip)`` with kind
``source``, pinned by ``tests/test_golden.py``). The three shapes here are pure traffic;
the screen learns which of them carry an alert from the endpoint.

**Two sources, one shape.** :class:`InProcessFlowRollup` is what a deployment without a
database has and :mod:`app.services.flow_store` is what one with a database has; both
answer with a :class:`FlowAggregate`. The rollup is a *rollup* rather than a buffer of
records: 5,000 flows/s would make a record buffer a leak with a retention window for a
lid, while the three questions the screen asks need per-minute, per-address and per-pair
totals and nothing else.

**Every tally is kept per minute and per dimension**, not per read. An edge's weight is
"flows between these two addresses *inside the requested window*", and a tally folded
over the whole retention could not answer a window in the middle of it -- which a
brushable series has to be able to do. Minute buckets are the atoms; a read re-buckets
them at whatever resolution the client asked for. The protocol and direction filters are
*keys* of the tallies rather than predicates applied at write time, because a rollup
cannot un-count a record it folded: a ``protocol=tcp`` read has to be an answer about the
traffic, not an answer about what happened to be folded first.

**What the rollup cannot do, it says.** Its resolution is a minute, so a window that
starts or ends inside a minute includes that whole minute (the store, grouping in SQL,
is exact). Its caps bound memory, and a record whose address or pair could not be
tracked is still counted in the buckets and the totals -- so the totals are complete
while the breakdown is not, and ``untracked_address_flows``/``untracked_pair_flows`` are
what the caveats name. Nothing here is a store and it does not pretend to be one: like
the log tail, it dies with the process.

The rules the fold keeps are T-416's, applied to traffic: a bucket's total is every flow
in it, a cap says it is a cap, and an ordering is total (flows descending, address
ascending) so two reads of one window produce the same screen.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.schemas.ingest import FlowRecordIn

__all__ = [
    "DEFAULT_FLOW_BUCKET_MINUTES",
    "DEFAULT_FLOW_EDGE_LIMIT",
    "DEFAULT_FLOW_ENTITY_LIMIT",
    "FLOW_BUCKET_MINUTES_MAX",
    "FLOW_EDGE_LIMIT_MAX",
    "FLOW_ENTITY_LIMIT_MAX",
    "FLOW_ROLLUP_MINUTES",
    "MAX_ROLLUP_EDGES",
    "MAX_ROLLUP_ENTRIES",
    "MAX_ROLLUP_NODES",
    "FlowAggregate",
    "FlowBucket",
    "FlowEdge",
    "FlowFilters",
    "FlowNode",
    "FlowTotals",
    "FlowWindow",
    "InProcessFlowRollup",
    "bucket_index",
    "bucket_starts",
]

#: The rollup's retention: one hour, the widest range the explorer offers.
FLOW_ROLLUP_MINUTES = 60

#: Five minutes: a day-long window then draws 288 buckets, not 1,440.
DEFAULT_FLOW_BUCKET_MINUTES = 5
#: A bucket wider than a day makes the series a single bar for most windows.
FLOW_BUCKET_MINUTES_MAX = 1_440

#: design.md §4.4 draws a short entity list, and the graph is drawn from it.
DEFAULT_FLOW_ENTITY_LIMIT = 25
FLOW_ENTITY_LIMIT_MAX = 200
#: More edges than nodes: a graph is relationships, and the threshold control trims.
DEFAULT_FLOW_EDGE_LIMIT = 200
FLOW_EDGE_LIMIT_MAX = 1_000

#: design.md §4.4 switches the graph to an adjacency matrix beyond 2,000 nodes.
MAX_ROLLUP_NODES = 2_000
#: Pairs, not nodes: a fully meshed 2,000-node graph would be two million edges.
MAX_ROLLUP_EDGES = 20_000
#: The bound that actually bounds memory: a pathological minute cannot keep more.
MAX_ROLLUP_ENTRIES = 200_000


#: The dimensions a tally is keyed by: the minute, the protocol, the direction.
_Dimension = tuple[datetime, str, str]


def _minute_of(at: datetime) -> datetime:
    """The minute an instant belongs to, on the UTC grid."""
    return at.astimezone(UTC).replace(second=0, microsecond=0)


def _minute_in_window(minute: datetime, window: FlowWindow) -> bool:
    """Whether a rolled-up minute overlaps the window.

    The rollup's atom is a minute, so a window that starts or ends inside one *includes
    that whole minute* -- the caveat says so, and an implementation that tested the
    minute's start for containment instead would answer a 10:00:30 window with nothing
    while its own caveat promised otherwise. Overlap is the honest test for a coarse
    atom; a store, which counts instants, stays exact (T-418).
    """
    return minute < window.end and minute + timedelta(minutes=1) > window.start


@dataclass(frozen=True, slots=True)
class FlowWindow:
    """A half-open time window: the bound every read and write here works inside.

    Half-open for the reason R-34 gives: two adjacent windows must not both claim a
    record that sits exactly on the boundary, or a series would double-count it and a
    total would not be the sum of its buckets.

    Attributes:
        start: inclusive lower bound.
        end: exclusive upper bound.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Refuse an inverted window, once, where it is built."""
        if self.end <= self.start:
            msg = f"a window must end after it starts, got {self.start} -> {self.end}"
            raise ValueError(msg)

    @property
    def span_seconds(self) -> float:
        """How wide the window is, in seconds."""
        return (self.end - self.start).total_seconds()

    def contains(self, at: datetime) -> bool:
        """Whether an instant falls inside, half-open on the right."""
        return self.start <= at < self.end


@dataclass(frozen=True, slots=True)
class FlowFilters:
    """What a read narrows the traffic by, before any grouping.

    Attributes:
        protocol: ``tcp``, ``udp`` or ``icmp``, or ``None`` for every protocol.
        direction: ``inbound``, ``outbound`` or ``internal``, or ``None`` for all.
    """

    protocol: str | None = None
    direction: str | None = None

    def allows(self, protocol: str, direction: str) -> bool:
        """Whether a rolled-up dimension survives the filters.

        The two callers are the read (which asks this of every key it iterates) and
        itself: there is no record-shaped predicate here, because the rollup never
        filters on the way in -- a tally it dropped could not be asked for later.
        """
        if self.protocol is not None and protocol != self.protocol:
            return False
        return self.direction is None or direction == self.direction


@dataclass(frozen=True, slots=True)
class FlowBucket:
    """One point of the volume series.

    Attributes:
        start: the bucket's inclusive lower bound.
        flows: how many flow records fell in it.
        bytes: the bytes those records carried.
        packets: the packets they carried.
    """

    start: datetime
    flows: int
    bytes: int
    packets: int


@dataclass(frozen=True, slots=True)
class FlowNode:
    """One address's share of the window.

    Attributes:
        ip: the address, as it appeared on the wire.
        flows: records in which it was an end.
        bytes: the bytes those records carried.
        packets: the packets they carried.
        inbound: records in which it was the destination.
        outbound: records in which it was the source.
        first_seen: the oldest record it appeared in, inside the window.
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
class FlowEdge:
    """One relationship: two addresses that exchanged traffic in the window.

    Attributes:
        source: the source address. ``a -> b`` and ``b -> a`` are two edges, not one:
            a flow count is directional, and merging the directions would lose what a
            responder is looking for.
        target: the destination address.
        flows: records between them, in that direction.
        bytes: the bytes those records carried.
    """

    source: str
    target: str
    flows: int
    bytes: int


@dataclass(frozen=True, slots=True)
class FlowTotals:
    """The window's totals, and what each cap did to them.

    Attributes:
        flows: records in the window -- **every** record, not a page of them.
        bytes: the bytes they carried.
        packets: the packets they carried.
        nodes: distinct addresses seen.
        edges: distinct directional pairs seen.
        nodes_capped: whether the entity list is a top-N of more addresses.
        edges_capped: whether the edge list is a top-N of more pairs.
        untracked_address_flows: records the rollup could not attribute to an address
            because it was full. They are in ``flows`` and in the series either way.
        untracked_pair_flows: the same, for the edge breakdown.
    """

    flows: int
    bytes: int
    packets: int
    nodes: int
    edges: int
    nodes_capped: bool
    edges_capped: bool
    untracked_address_flows: int
    untracked_pair_flows: int


@dataclass(frozen=True, slots=True)
class FlowAggregate:
    """What a flow read answers with: three panels and the counts behind them.

    Attributes:
        series: one bucket per interval, tiling the window exactly.
        entities: the addresses, busiest first, capped.
        edges: the relationships, heaviest first, capped.
        totals: the window's counts, including every cap that shaped the lists.
    """

    series: list[FlowBucket]
    entities: list[FlowNode]
    edges: list[FlowEdge]
    totals: FlowTotals


def bucket_starts(start: datetime, end: datetime, bucket_minutes: int) -> list[datetime]:
    """The inclusive start of every bucket tiling ``[start, end)``.

    Raises:
        ValueError: if ``bucket_minutes`` is not positive, or the window is inverted.
    """
    if bucket_minutes < 1:
        msg = f"bucket_minutes must be positive, got {bucket_minutes}"
        raise ValueError(msg)
    if end <= start:
        msg = "a series window must end after it starts"
        raise ValueError(msg)
    width = timedelta(minutes=bucket_minutes)
    starts: list[datetime] = []
    cursor = start
    while cursor < end:
        starts.append(cursor)
        cursor = cursor + width
    return starts


def bucket_index(at: datetime, start: datetime, bucket_minutes: int, count: int) -> int:
    """Which bucket an instant belongs to, clamped into ``[0, count)``.

    A record on or after the window's end is clamped into the last bucket rather than
    dropped (T-416's rule): a series whose total is smaller than the window's flow
    count loses its tail silently, and the tail is usually the interesting part.
    """
    width = timedelta(minutes=bucket_minutes)
    index = int((at - start) / width)
    return min(max(index, 0), count - 1)


@dataclass(slots=True)
class _Bucket:
    """A minute's traffic, inside the rollup."""

    flows: int = 0
    bytes: int = 0
    packets: int = 0


@dataclass(slots=True)
class _Node:
    """One address's traffic inside one minute."""

    flows: int = 0
    bytes: int = 0
    packets: int = 0
    inbound: int = 0
    outbound: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def count(self, record: FlowRecordIn, *, total_bytes: int, role: str) -> None:
        """Count one record into this address's tally, in the given ``role``."""
        self.flows += 1
        self.bytes += total_bytes
        self.packets += record.packets
        if role == "source":
            self.outbound += 1
        else:
            self.inbound += 1
        self._stretch(record.timestamp)

    def _stretch(self, at: datetime) -> None:
        """Widen the tally's span to include one instant."""
        if self.first_seen is None or at < self.first_seen:
            self.first_seen = at
        if self.last_seen is None or at > self.last_seen:
            self.last_seen = at

    def merged_with(self, other: _Node) -> _Node:
        """A copy of this tally with another minute's folded into it."""
        merged = _Node(
            flows=self.flows + other.flows,
            bytes=self.bytes + other.bytes,
            packets=self.packets + other.packets,
            inbound=self.inbound + other.inbound,
            outbound=self.outbound + other.outbound,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
        )
        if other.first_seen is not None:
            merged._stretch(other.first_seen)
        if other.last_seen is not None:
            merged._stretch(other.last_seen)
        return merged

    def frozen(self, ip: str) -> FlowNode:
        """This tally as the response's shape."""
        return FlowNode(
            ip=ip,
            flows=self.flows,
            bytes=self.bytes,
            packets=self.packets,
            inbound=self.inbound,
            outbound=self.outbound,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
        )


@dataclass(slots=True)
class _Edge:
    """One directional pair's traffic inside one minute."""

    flows: int = 0
    bytes: int = 0

    def merged_with(self, other: _Edge) -> _Edge:
        """A copy of this tally with another minute's folded into it."""
        return _Edge(flows=self.flows + other.flows, bytes=self.bytes + other.bytes)

    def frozen(self, source: str, target: str) -> FlowEdge:
        """This tally as the response's shape."""
        return FlowEdge(source=source, target=target, flows=self.flows, bytes=self.bytes)


class InProcessFlowRollup:
    """The rollup a deployment without a database reads from (T-418).

    Bounded three ways, and what each bound costs is reported on the read rather than
    applied silently:

    * **Age.** Minutes older than :data:`FLOW_ROLLUP_MINUTES` are dropped, and the
      oldest minute still held is on the response, so a window reaching past the start
      says so instead of drawing an empty left half.
    * **Addresses and pairs.** Beyond :data:`MAX_ROLLUP_NODES` addresses or
      :data:`MAX_ROLLUP_EDGES` pairs, new entries are refused; those records are still
      counted in the buckets and the totals, and each refusal is counted per flow.
    * **Entries.** :data:`MAX_ROLLUP_ENTRIES` minute-entries in total, which is what
      actually bounds memory against a pathological minute.

    Tallies are keyed by ``(minute, protocol, direction)`` plus the address or the pair,
    so the read's filters are exact: ``protocol=tcp`` sums the tcp keys and never has to
    guess what the write side decided to keep.
    """

    __slots__ = (
        "_buckets",
        "_dropped_minutes",
        "_edges",
        "_entries",
        "_max_age_minutes",
        "_max_edges",
        "_max_entries",
        "_max_nodes",
        "_nodes",
        "_untracked_address_flows",
        "_untracked_pair_flows",
        "max_age_seconds",
    )

    def __init__(
        self,
        *,
        retention_minutes: int = FLOW_ROLLUP_MINUTES,
        max_nodes: int = MAX_ROLLUP_NODES,
        max_edges: int = MAX_ROLLUP_EDGES,
        max_entries: int = MAX_ROLLUP_ENTRIES,
    ) -> None:
        """Start empty, with the three caps in hand.

        Raises:
            ValueError: if any cap is not positive, so a misconfiguration stops a
                process rather than showing up as an empty graph.
        """
        for name, value in (
            ("retention_minutes", retention_minutes),
            ("max_nodes", max_nodes),
            ("max_edges", max_edges),
            ("max_entries", max_entries),
        ):
            if value < 1:
                msg = f"{name} must be positive, got {value}"
                raise ValueError(msg)
        self._max_age_minutes = retention_minutes
        self.max_age_seconds = float(retention_minutes * 60)
        self._max_nodes = max_nodes
        self._max_edges = max_edges
        self._max_entries = max_entries
        # A dict rather than a deque: records may arrive out of order (a replay, a
        # producer retry), and a deque's "the newest minute is the last one appended"
        # would then merge two different minutes into one bucket.
        self._buckets: dict[_Dimension, _Bucket] = {}
        self._nodes: dict[tuple[_Dimension, str], _Node] = {}
        self._edges: dict[tuple[_Dimension, str, str], _Edge] = {}
        self._entries = 0
        self._dropped_minutes = 0
        self._untracked_address_flows = 0
        self._untracked_pair_flows = 0

    def append(self, records: Sequence[FlowRecordIn]) -> int:
        """Count a batch of accepted records into the rollup, returning how many.

        The caller passes accepted records only -- the ingest route validates and
        admits a batch before this is reached -- so the return is the number handed in,
        and a batch of zero is a no-op rather than an empty minute.
        """
        if not records:
            return 0
        newest: datetime | None = None
        for record in records:
            if newest is None or record.timestamp > newest:
                newest = record.timestamp
            self._add(record)
        if newest is not None:
            self._prune(newest)
        return len(records)

    def _add(self, record: FlowRecordIn) -> None:
        """Count one record into its minute's three tallies."""
        dimension: _Dimension = (
            _minute_of(record.timestamp),
            record.protocol.value,
            record.direction.value,
        )
        total_bytes = record.src_bytes + record.dst_bytes
        bucket = self._buckets.get(dimension)
        if bucket is None:
            bucket = _Bucket()
            self._buckets[dimension] = bucket
        bucket.flows += 1
        bucket.bytes += total_bytes
        bucket.packets += record.packets

        # One record is counted once even when *both* of its ends were refused: the
        # counter says how many records the address breakdown could not take, and a
        # per-end count would report a single record as two (T-416's completeness rule
        # is about records, so the number that qualifies it must be too).
        source = self._node_for(dimension, str(record.src_ip))
        destination = self._node_for(dimension, str(record.dst_ip))
        if source is None or destination is None:
            self._untracked_address_flows += 1
        if source is not None:
            source.count(record, total_bytes=total_bytes, role="source")
        if destination is not None:
            destination.count(record, total_bytes=total_bytes, role="destination")

        edge = self._edge_for(dimension, str(record.src_ip), str(record.dst_ip))
        if edge is None:
            self._untracked_pair_flows += 1
        else:
            edge.flows += 1
            edge.bytes += total_bytes

    def _room(self, *, kind: str) -> bool:
        """Whether one more entry of ``kind`` may be tracked."""
        if self._entries >= self._max_entries:
            return False
        if kind == "node":
            return len(self._nodes) < self._max_nodes
        return len(self._edges) < self._max_edges

    def _node_for(self, dimension: _Dimension, ip: str) -> _Node | None:
        """The address's tally in that minute, or ``None`` when the caps refuse one."""
        key = (dimension, ip)
        node = self._nodes.get(key)
        if node is not None:
            return node
        if not self._room(kind="node"):
            return None
        node = _Node()
        self._nodes[key] = node
        self._entries += 1
        return node

    def _edge_for(self, dimension: _Dimension, source: str, target: str) -> _Edge | None:
        """The pair's tally in that minute, or ``None`` when the caps refuse one."""
        key = (dimension, source, target)
        edge = self._edges.get(key)
        if edge is not None:
            return edge
        if not self._room(kind="edge"):
            return None
        edge = _Edge()
        self._edges[key] = edge
        self._entries += 1
        return edge

    def _prune(self, newest: datetime) -> None:
        """Drop tallies older than the retention, measured from the newest record.

        From the newest *record* rather than the wall clock: the rollup is fed by a
        stream, and a replay of an hour ago would otherwise evict everything it was
        replaying. What it dropped is counted, not forgotten.
        """
        cutoff = _minute_of(newest) - timedelta(minutes=self._max_age_minutes - 1)
        stale_buckets = [key for key in self._buckets if key[0] < cutoff]
        for key in stale_buckets:
            del self._buckets[key]
            self._dropped_minutes += 1
        # Each store pruned in its own loop rather than a tuple of the two: their keys
        # have different shapes, and one loop over both would have to forget that (which
        # is also what a type checker refuses to let through).
        for node_key in [key for key in self._nodes if key[0][0] < cutoff]:
            del self._nodes[node_key]
            self._entries -= 1
        for edge_key in [key for key in self._edges if key[0][0] < cutoff]:
            del self._edges[edge_key]
            self._entries -= 1

    @property
    def retained_from(self) -> datetime | None:
        """The oldest minute the rollup still holds, or ``None`` when it is empty."""
        return min((key[0] for key in self._buckets), default=None)

    @property
    def retained_to(self) -> datetime | None:
        """The newest minute the rollup still holds, or ``None`` when it is empty."""
        return max((key[0] for key in self._buckets), default=None)

    @property
    def dropped_minutes(self) -> int:
        """How many minute-entries have aged out since the process started."""
        return self._dropped_minutes

    @property
    def untracked_address_flows(self) -> int:
        """Records the address breakdown could not fully take, the rollup being full.

        A record with one refused end counts once: it is a record the per-address
        breakdown is missing part of, and ``flows`` still holds it either way.
        """
        return self._untracked_address_flows

    @property
    def untracked_pair_flows(self) -> int:
        """Records the pair breakdown could not take, because the rollup was full."""
        return self._untracked_pair_flows

    def summary(
        self,
        window: FlowWindow,
        *,
        bucket_minutes: int = DEFAULT_FLOW_BUCKET_MINUTES,
        entity_limit: int = DEFAULT_FLOW_ENTITY_LIMIT,
        edge_limit: int = DEFAULT_FLOW_EDGE_LIMIT,
        filters: FlowFilters | None = None,
    ) -> FlowAggregate:
        """Aggregate the window from the retained minutes.

        Args:
            window: the half-open range to answer about.
            bucket_minutes: the series' resolution.
            entity_limit: how many addresses the response lists.
            edge_limit: how many relationships it lists.
            filters: protocol and direction narrowing, applied to the keys.

        Returns:
            The three panels, with the caps that shaped them reported in
            :class:`FlowTotals` rather than applied invisibly.

        Raises:
            ValueError: if ``bucket_minutes`` is not positive or the window is inverted.
        """
        chosen = filters or FlowFilters()
        starts = bucket_starts(window.start, window.end, bucket_minutes)
        buckets = [FlowBucket(start=start, flows=0, bytes=0, packets=0) for start in starts]
        flows = 0
        total_bytes = 0
        packets = 0

        for (minute, protocol, direction), bucket in self._buckets.items():
            if not _minute_in_window(minute, window) or not chosen.allows(protocol, direction):
                continue
            index = bucket_index(minute, window.start, bucket_minutes, len(starts))
            point = buckets[index]
            buckets[index] = FlowBucket(
                start=point.start,
                flows=point.flows + bucket.flows,
                bytes=point.bytes + bucket.bytes,
                packets=point.packets + bucket.packets,
            )
            flows += bucket.flows
            total_bytes += bucket.bytes
            packets += bucket.packets

        nodes: dict[str, _Node] = {}
        for (minute, protocol, direction, ip), node in _iter_nodes(self._nodes):
            if not _minute_in_window(minute, window) or not chosen.allows(protocol, direction):
                continue
            existing = nodes.get(ip)
            nodes[ip] = node if existing is None else existing.merged_with(node)

        edges: dict[tuple[str, str], _Edge] = {}
        for (minute, protocol, direction, source, target), edge in _iter_edges(self._edges):
            if not _minute_in_window(minute, window) or not chosen.allows(protocol, direction):
                continue
            key = (source, target)
            existing_edge = edges.get(key)
            edges[key] = edge if existing_edge is None else existing_edge.merged_with(edge)

        node_rows = [tally.frozen(ip) for ip, tally in nodes.items()]
        node_rows.sort(key=lambda node: (-node.flows, -node.bytes, node.ip))
        edge_rows = [tally.frozen(source, target) for (source, target), tally in edges.items()]
        edge_rows.sort(key=lambda edge: (-edge.flows, -edge.bytes, edge.source, edge.target))

        return FlowAggregate(
            series=buckets,
            entities=node_rows[:entity_limit],
            edges=edge_rows[:edge_limit],
            totals=FlowTotals(
                flows=flows,
                bytes=total_bytes,
                packets=packets,
                nodes=len(node_rows),
                edges=len(edge_rows),
                nodes_capped=len(node_rows) > entity_limit,
                edges_capped=len(edge_rows) > edge_limit,
                untracked_address_flows=self._untracked_address_flows,
                untracked_pair_flows=self._untracked_pair_flows,
            ),
        )


def _iter_nodes(
    store: dict[tuple[_Dimension, str], _Node],
) -> Iterable[tuple[tuple[datetime, str, str, str], _Node]]:
    """Flatten a keyed node store into ``((minute, protocol, direction, ip), tally)``.

    A flat tuple rather than the store's nested key, because the caller's job is to
    compare it against a window and the filters: the key it iterates should be the
    shape it reads, not a key it has to unpack again (a mistake this function made once
    and a test now refuses: rebuilding a flat key and indexing the store with it raised
    ``KeyError`` on every non-empty read).
    """
    for key, node in store.items():
        dimension, ip = key
        yield (*dimension, ip), node


def _iter_edges(
    store: dict[tuple[_Dimension, str, str], _Edge],
) -> Iterable[tuple[tuple[datetime, str, str, str, str], _Edge]]:
    """Flatten a keyed edge store into ``((minute, protocol, direction, src, dst), tally)``."""
    for key, edge in store.items():
        dimension, source, target = key
        yield (*dimension, source, target), edge
