"""The in-process flow rollup (T-418).

The rollup is the source a deployment without a database reads, and the acceptance
criterion it has to satisfy is the same one T-416 set for the overview: **counts are
complete for the window rather than capped at 5,000 rows**. Four properties carry that
here, and each is a place a rollup normally loses data:

* **Filters are dimensions, not predicates.** Every tally is keyed
  ``(minute, protocol, direction)``, so ``protocol=tcp`` sums the tcp keys. A read-time
  predicate over merged tallies cannot separate what it merged, and a write-time discard
  cannot be asked for later -- both are defects this file would catch.
* **A cap refuses entries, never counts.** Past the node or edge cap the record still
  lands in the bucket, and the refusal is counted per record (once, even when both ends
  were refused) so the response can say the breakdown is partial while the totals are not.
* **The window is half-open.** A record exactly on a boundary belongs to one side of it,
  which is what makes a series' buckets sum to its totals.
* **Age is measured from the newest record, not the clock.** A replay of an hour ago must
  not evict everything it is replaying, and what ages out is counted rather than
  forgotten.

No database is involved: this is arithmetic over dicts, and ``test_flow_store.py`` is
where the other source is tested.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.schemas.ingest import Direction, FlowRecordIn, Protocol
from app.services.flow_read_model import (
    DEFAULT_FLOW_BUCKET_MINUTES,
    FLOW_BUCKET_MINUTES_MAX,
    FLOW_ROLLUP_MINUTES,
    FlowFilters,
    FlowWindow,
    InProcessFlowRollup,
    bucket_index,
    bucket_starts,
)

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)


def record(
    *,
    at: datetime | None = None,
    src: str = "10.0.0.1",
    dst: str = "10.0.0.2",
    protocol: Protocol = Protocol.TCP,
    direction: Direction = Direction.OUTBOUND,
    src_bytes: int = 100,
    dst_bytes: int = 40,
    packets: int = 3,
) -> FlowRecordIn:
    """One accepted flow record, with the fields the rollup reads defaulted."""
    return FlowRecordIn(
        timestamp=at or START,
        src_ip=src,  # type: ignore[arg-type]
        dst_ip=dst,  # type: ignore[arg-type]
        protocol=protocol,
        direction=direction,
        src_port=12345,
        dst_port=443,
        packets=packets,
        src_packets=packets,
        dst_packets=0,
        src_bytes=src_bytes,
        dst_bytes=dst_bytes,
        duration=1.0,
    )


def window(*, minutes: int = 5, start: datetime | None = None) -> FlowWindow:
    """A window starting at :data:`START` unless told otherwise."""
    beginning = start or START
    return FlowWindow(start=beginning, end=beginning + timedelta(minutes=minutes))


class TestBucketGrid:
    """The series tiles the window, on a grid the store can reproduce."""

    def test_the_buckets_tile_the_window_exactly(self) -> None:
        starts = bucket_starts(START, START + timedelta(minutes=10), 3)

        assert len(starts) == 4
        assert starts[0] == START
        assert starts[-1] == START + timedelta(minutes=9)

    def test_a_partial_final_bucket_is_still_offered(self) -> None:
        # Four minutes at three-minute resolution: the last bucket is short, and a
        # series that dropped it would lose the newest traffic on the screen.
        starts = bucket_starts(START, START + timedelta(minutes=4), 3)

        assert len(starts) == 2

    def test_the_index_of_a_late_record_is_clamped_into_the_last_bucket(self) -> None:
        # ``date_bin`` cannot produce a bucket outside the window, and neither may the
        # rollup: an out-of-range index would be an IndexError on a live read.
        index = bucket_index(START + timedelta(minutes=99), START, 5, 3)

        assert index == 2

    def test_a_record_before_the_window_lands_in_the_first_bucket(self) -> None:
        index = bucket_index(START - timedelta(minutes=2), START, 5, 3)

        assert index == 0


class TestTheRollupCounts:
    """Totals, bytes and packets, from the records handed in."""

    def test_one_record_lands_in_its_minute_and_nowhere_else(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(at=START + timedelta(seconds=30))])

        summary = rollup.summary(window(minutes=2), bucket_minutes=1)

        assert [bucket.flows for bucket in summary.series] == [1, 0]
        assert summary.totals.flows == 1
        assert summary.totals.bytes == 140
        assert summary.totals.packets == 3

    def test_records_of_the_same_minute_share_one_bucket(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [record(at=START), record(at=START + timedelta(seconds=59), src_bytes=10, dst_bytes=0)]
        )

        summary = rollup.summary(window(minutes=1), bucket_minutes=1)

        assert summary.series[0].flows == 2
        assert summary.series[0].bytes == 150

    def test_the_series_sums_to_the_totals(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(at=START + timedelta(minutes=index)) for index in range(4)])

        summary = rollup.summary(window(minutes=4), bucket_minutes=2)

        assert sum(bucket.flows for bucket in summary.series) == summary.totals.flows
        assert [bucket.flows for bucket in summary.series] == [2, 2]

    def test_a_window_that_starts_mid_bucket_still_counts_the_whole_minute(self) -> None:
        # The rollup's granularity is a minute and the caveat says so: a request for
        # 10:00:30-10:01:00 includes the 10:00 minute in full rather than nothing.
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(at=START)])

        summary = rollup.summary(
            FlowWindow(start=START + timedelta(seconds=30), end=START + timedelta(minutes=1)),
            bucket_minutes=1,
        )

        assert summary.totals.flows == 1

    def test_the_minute_the_store_would_use_is_the_minute_counted(self) -> None:
        # ``10:00:59`` and ``10:00:00`` are one minute here; ``10:01:00`` is the next.
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(at=START + timedelta(seconds=59))])

        assert rollup.retained_from == START
        assert rollup.retained_to == START


class TestFiltersAreDimensions:
    """Filtering happens over keys, so it can never un-count what it never merged."""

    def test_a_protocol_filter_sums_only_its_own_keys(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(protocol=Protocol.TCP),
                record(protocol=Protocol.UDP),
                record(protocol=Protocol.UDP),
            ]
        )

        tcp = rollup.summary(window(), filters=FlowFilters(protocol="tcp"))
        udp = rollup.summary(window(), filters=FlowFilters(protocol="udp"))

        assert tcp.totals.flows == 1
        assert udp.totals.flows == 2
        assert tcp.series[0].flows == 1

    def test_a_direction_filter_sums_only_its_own_keys(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(direction=Direction.INBOUND),
                record(direction=Direction.OUTBOUND),
                record(direction=Direction.OUTBOUND),
            ]
        )

        inbound = rollup.summary(window(), filters=FlowFilters(direction="inbound"))
        outbound = rollup.summary(window(), filters=FlowFilters(direction="outbound"))

        # The filter narrows on the record's own direction label; a node's
        # inbound/outbound counters are structural (was it the destination or the
        # source), which is why an "inbound" record still counts 10.0.0.1 as a sender.
        assert inbound.totals.flows == 1
        assert outbound.totals.flows == 2
        assert inbound.entities[0].outbound == 1

    def test_both_filters_together_are_an_intersection(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(protocol=Protocol.TCP, direction=Direction.INBOUND),
                record(protocol=Protocol.TCP, direction=Direction.OUTBOUND),
                record(protocol=Protocol.UDP, direction=Direction.INBOUND),
            ]
        )

        narrowed = rollup.summary(
            window(), filters=FlowFilters(protocol="tcp", direction="inbound")
        )

        assert narrowed.totals.flows == 1
        assert narrowed.totals.edges == 1

    def test_a_filter_that_matches_nothing_is_empty_rather_than_everything(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(protocol=Protocol.TCP)])

        icmp = rollup.summary(window(), filters=FlowFilters(protocol="icmp"))

        assert icmp.totals.flows == 0
        assert icmp.entities == []

    def test_the_entities_and_edges_respect_the_filter_too(self) -> None:
        # The defect this pins: a rollup that filtered its buckets but not its
        # per-address tallies, which would draw a graph of traffic the filter excluded.
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(src="10.0.0.1", dst="10.0.0.2", protocol=Protocol.TCP),
                record(src="10.0.0.3", dst="10.0.0.4", protocol=Protocol.UDP),
            ]
        )

        tcp = rollup.summary(window(), filters=FlowFilters(protocol="tcp"))

        assert [node.ip for node in tcp.entities] == ["10.0.0.1", "10.0.0.2"]
        assert tcp.totals.nodes == 2
        assert [edge.source for edge in tcp.edges] == ["10.0.0.1"]


class TestAddressesAndEdges:
    """Both ends of a record are addresses; both directions are edges."""

    def test_an_address_that_only_receives_is_still_listed(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(src="10.0.0.1", dst="10.0.0.2")])

        summary = rollup.summary(window())

        by_ip = {node.ip: node for node in summary.entities}
        assert set(by_ip) == {"10.0.0.1", "10.0.0.2"}
        assert by_ip["10.0.0.2"].inbound == 1
        assert by_ip["10.0.0.2"].outbound == 0
        assert by_ip["10.0.0.1"].outbound == 1

    def test_both_ends_carry_the_records_bytes(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(src_bytes=100, dst_bytes=40)])

        summary = rollup.summary(window())

        assert {node.ip: node.bytes for node in summary.entities} == {
            "10.0.0.1": 140,
            "10.0.0.2": 140,
        }

    def test_edges_are_directional(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(src="10.0.0.1", dst="10.0.0.2"),
                record(src="10.0.0.2", dst="10.0.0.1"),
                record(src="10.0.0.1", dst="10.0.0.2"),
            ]
        )

        summary = rollup.summary(window())

        pairs = {(edge.source, edge.target): edge.flows for edge in summary.edges}
        assert pairs == {("10.0.0.1", "10.0.0.2"): 2, ("10.0.0.2", "10.0.0.1"): 1}
        assert summary.totals.edges == 2

    def test_the_addresses_span_the_window_they_were_seen_in(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(at=START, src="10.0.0.1", dst="10.0.0.2"),
                record(at=START + timedelta(minutes=1), src="10.0.0.1", dst="10.0.0.2"),
            ]
        )

        summary = rollup.summary(window(minutes=2))

        node = next(node for node in summary.entities if node.ip == "10.0.0.1")
        assert node.first_seen == START
        assert node.last_seen == START + timedelta(minutes=1)

    def test_the_busiest_address_is_listed_first(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append(
            [
                record(src="10.0.0.9", dst="10.0.0.1"),
                record(src="10.0.0.9", dst="10.0.0.1"),
                record(src="10.0.0.9", dst="10.0.0.2"),
            ]
        )

        summary = rollup.summary(window())

        assert [node.ip for node in summary.entities][0] == "10.0.0.9"
        assert summary.entities[0].flows == 3


class TestCapsRefuseEntriesNotCounts:
    """A full rollup loses breakdowns and says so; it does not lose records."""

    def test_a_node_cap_keeps_the_record_in_the_totals(self) -> None:
        # Four addresses fit (two pairs); the third pair is refused, and the record it
        # came from is still a record.
        rollup = InProcessFlowRollup(retention_minutes=10, max_nodes=4)
        rollup.append(
            [
                record(src="10.0.0.1", dst="10.0.0.2"),
                record(src="10.0.0.3", dst="10.0.0.4"),
                record(src="10.0.0.5", dst="10.0.0.6"),
            ]
        )

        summary = rollup.summary(window())

        assert summary.totals.flows == 3
        assert sum(bucket.flows for bucket in summary.series) == 3
        assert summary.totals.untracked_address_flows == 1

    def test_a_record_with_both_ends_refused_is_counted_once(self) -> None:
        # The counter qualifies a record count, so it must be a record count: an
        # implementation that incremented per end would report one record as two.
        rollup = InProcessFlowRollup(retention_minutes=10, max_nodes=1)
        rollup.append([record(src="10.0.0.1", dst="10.0.0.1")])
        rollup.append([record(src="10.0.0.8", dst="10.0.0.9")])

        summary = rollup.summary(window())

        assert summary.totals.flows == 2
        assert summary.totals.untracked_address_flows == 1

    def test_an_edge_cap_keeps_the_record_in_the_totals(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10, max_edges=1)

        rollup.append([record(src="10.0.0.1", dst="10.0.0.2")])
        rollup.append([record(src="10.0.0.3", dst="10.0.0.4")])

        summary = rollup.summary(window())

        assert summary.totals.flows == 2
        assert summary.totals.edges == 1
        assert summary.totals.untracked_pair_flows == 1

    def test_the_cap_reports_a_top_n_rather_than_a_population(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10, max_nodes=10)
        rollup.append([record(src=f"10.0.0.{index}", dst="10.0.0.254") for index in range(1, 6)])

        summary = rollup.summary(window(), entity_limit=3)

        assert summary.totals.nodes == 6
        assert summary.totals.nodes_capped is True
        assert len(summary.entities) == 3

    def test_an_uncapped_window_says_so(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(src="10.0.0.1", dst="10.0.0.2")])

        summary = rollup.summary(window(), entity_limit=25, edge_limit=200)

        assert summary.totals.nodes_capped is False
        assert summary.totals.edges_capped is False
        assert summary.totals.untracked_address_flows == 0
        assert summary.totals.untracked_pair_flows == 0

    def test_an_entry_cap_refuses_new_tallies_but_never_the_bucket(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10, max_entries=2)
        rollup.append([record(src="10.0.0.1", dst="10.0.0.2")])
        rollup.append([record(src="10.0.0.3", dst="10.0.0.4")])

        summary = rollup.summary(window())

        assert summary.totals.flows == 2
        assert summary.totals.untracked_address_flows == 1

    def test_the_totals_do_not_move_when_the_cap_does(self) -> None:
        # T-416's defect, restated for traffic: a count that came from the capped list
        # would change with the cap, and the screen's headline number would then be a
        # statement about the limit rather than about the traffic.
        records = [record(src=f"10.0.0.{index}", dst="10.0.0.254") for index in range(1, 8)]
        tight = InProcessFlowRollup(retention_minutes=10, max_nodes=50)
        tight.append(records)

        summary = tight.summary(window(), entity_limit=1)

        assert summary.totals.flows == len(records)
        assert summary.totals.nodes == 8

    def test_a_non_positive_cap_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="max_nodes must be positive"):
            InProcessFlowRollup(max_nodes=0)

    def test_a_non_positive_bucket_is_refused_at_read(self) -> None:
        rollup = InProcessFlowRollup()

        with pytest.raises(ValueError, match="bucket_minutes"):
            rollup.summary(window(), bucket_minutes=0)


class TestRetention:
    """Minutes age out from the newest record, and the drop is counted."""

    def test_a_minute_older_than_the_retention_is_dropped(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=2)
        rollup.append([record(at=START)])
        rollup.append([record(at=START + timedelta(minutes=5))])

        summary = rollup.summary(FlowWindow(start=START, end=START + timedelta(minutes=6)))

        assert summary.totals.flows == 1
        assert rollup.dropped_minutes == 1

    def test_the_newest_record_decides_what_is_old_not_the_clock(self) -> None:
        # A replay of an hour ago must not evict the minute it is replaying: the
        # cutoff comes from the batch's newest timestamp, not from ``now``.
        rollup = InProcessFlowRollup(retention_minutes=2)
        old = START - timedelta(hours=1)
        rollup.append([record(at=old), record(at=old + timedelta(minutes=1))])

        summary = rollup.summary(
            FlowWindow(start=old, end=old + timedelta(minutes=2)), bucket_minutes=1
        )

        assert summary.totals.flows == 2
        assert rollup.dropped_minutes == 0

    def test_the_default_retention_covers_the_widest_offered_window(self) -> None:
        # The traffic explorer offers 1h, which is exactly the rollup's default
        # retention: a smaller default would make the offered window partly unanswerable
        # in the deployment that has no database at all.
        assert FLOW_ROLLUP_MINUTES == 60

    def test_what_is_still_held_is_readable(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(at=START), record(at=START + timedelta(minutes=3))])

        assert rollup.retained_from == START
        assert rollup.retained_to == START + timedelta(minutes=3)

    def test_an_empty_rollup_holds_nothing_and_says_so(self) -> None:
        rollup = InProcessFlowRollup()

        assert rollup.retained_from is None
        assert rollup.retained_to is None

    def test_the_retention_is_exposed_as_seconds_for_the_route(self) -> None:
        rollup = InProcessFlowRollup(retention_minutes=90)

        assert rollup.max_age_seconds == 5_400.0


class TestAppendContract:
    """What the ingest route relies on."""

    def test_append_returns_how_many_it_kept(self) -> None:
        rollup = InProcessFlowRollup()

        assert rollup.append([record(), record()]) == 2
        assert rollup.append([]) == 0

    def test_an_empty_batch_does_not_create_a_minute(self) -> None:
        rollup = InProcessFlowRollup()

        rollup.append([])

        assert rollup.retained_from is None

    def test_the_rollup_keys_by_minute_not_by_arrival_order(self) -> None:
        # Out-of-order delivery (a retry, a replay) must not merge two minutes into one.
        rollup = InProcessFlowRollup(retention_minutes=10)
        rollup.append([record(at=START + timedelta(minutes=1))])
        rollup.append([record(at=START)])

        summary = rollup.summary(window(minutes=2), bucket_minutes=1)

        assert [bucket.flows for bucket in summary.series] == [1, 1]
        assert rollup.retained_from == START

    def test_the_default_bucket_is_a_fifth_of_an_hour(self) -> None:
        # 60 buckets over the widest offered window: the screen's own choice, pinned
        # here so a change to it is a change to a number a client may rely on.
        assert DEFAULT_FLOW_BUCKET_MINUTES == 5

    def test_the_bucket_max_is_a_day(self) -> None:
        assert FLOW_BUCKET_MINUTES_MAX == 1_440
