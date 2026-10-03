"""Tests for windowing (T-108).

The acceptance criterion is that window boundaries are deterministic given an
input stream, so the central test below asserts exact boundaries against a fixed
fixture rather than counting windows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aegis_ml.data.features import extract_flow_window
from aegis_ml.data.records import Direction, FlowRecord, LogLevel, LogRecord, Protocol
from aegis_ml.data.synthetic import GenerationSpec, Scenario, generate_flows, generate_logs
from aegis_ml.data.windowing import (
    Window,
    WindowKey,
    WindowTrigger,
    flow_key,
    log_key,
    window_flows,
    window_logs,
)

EPOCH = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


def stream(
    count: int,
    *,
    step: float = 1.0,
    src: str = "10.4.20.11",
    dst: str = "10.4.20.12",
    start: datetime = EPOCH,
) -> list[FlowRecord]:
    """Build a fixed, evenly spaced flow stream from one entity."""
    return [
        FlowRecord(
            timestamp=start + timedelta(seconds=index * step),
            src_ip=src,
            dst_ip=dst,
            src_port=51000 + index,
            dst_port=443,
            protocol=Protocol.TCP,
            direction=Direction.INTERNAL,
            packets=10,
            src_packets=5,
            dst_packets=5,
            src_bytes=1200,
            dst_bytes=3400,
            duration=0.5,
            label="normal",
        )
        for index in range(count)
    ]


def bounds(windows: tuple[Window[FlowRecord], ...]) -> list[tuple[int, int]]:
    """Reduce windows to (record count, index) pairs, for readable assertions."""
    return [(len(window.records), window.index) for window in windows]


# --- the acceptance criterion -------------------------------------------


def test_boundaries_are_exact_for_a_fixed_stream() -> None:
    """12 flows, window 5, default tumbling stride: three windows, no ambiguity."""
    windows = window_flows(stream(12), size=5)

    assert bounds(windows) == [(5, 0), (5, 1), (2, 2)]
    assert [window.trigger for window in windows] == [
        WindowTrigger.COUNT,
        WindowTrigger.COUNT,
        WindowTrigger.END_OF_STREAM,
    ]
    assert windows[0].start == EPOCH
    assert windows[0].end == EPOCH + timedelta(seconds=4)
    assert windows[1].start == EPOCH + timedelta(seconds=5)
    assert windows[2].start == EPOCH + timedelta(seconds=10)
    assert windows[2].end == EPOCH + timedelta(seconds=11)
    assert [window.is_complete for window in windows] == [True, True, False]
    assert all(window.key == "10.4.20.11" for window in windows)
    assert all(window.key_kind == "source" for window in windows)


def test_boundaries_are_exact_when_sliding() -> None:
    """Stride 2 over 12 records: offsets 0, 2, 4, 6, then the leftover tail."""
    windows = window_flows(stream(12), size=5, stride=2)

    assert [len(window.records) for window in windows] == [5, 5, 5, 5, 1]
    assert windows[3].start == EPOCH + timedelta(seconds=6)
    assert windows[4].start == EPOCH + timedelta(seconds=11)
    assert windows[4].trigger is WindowTrigger.END_OF_STREAM


def test_an_exactly_filled_stream_has_no_partial_window() -> None:
    windows = window_flows(stream(10), size=5)

    assert bounds(windows) == [(5, 0), (5, 1)]
    assert all(window.trigger is WindowTrigger.COUNT for window in windows)


def test_a_stream_shorter_than_one_window_yields_one_partial() -> None:
    windows = window_flows(stream(3), size=50)

    assert bounds(windows) == [(3, 0)]
    assert windows[0].trigger is WindowTrigger.END_OF_STREAM
    assert windows[0].is_complete is False


def test_windowing_is_deterministic() -> None:
    flows = stream(37)

    assert window_flows(flows, size=5) == window_flows(flows, size=5)


# --- entity partitioning -------------------------------------------------


def test_each_entity_gets_its_own_windows() -> None:
    flows = sorted(
        stream(6, src="10.4.20.11") + stream(4, src="10.4.20.13"), key=lambda f: f.timestamp
    )

    windows = window_flows(flows, size=5)

    assert [window.key for window in windows] == [
        "10.4.20.11",
        "10.4.20.11",
        "10.4.20.13",
    ], "keys are visited in sorted order"
    assert bounds(windows) == [(5, 0), (1, 1), (4, 0)], "indices restart per key"


def test_key_order_does_not_depend_on_input_order() -> None:
    a = stream(3, src="10.4.20.11")
    b = stream(3, src="10.4.20.13")
    forward = window_flows(sorted(a + b, key=lambda f: f.timestamp), size=3)
    backward = window_flows(sorted(b + a, key=lambda f: f.timestamp), size=3)

    assert forward == backward


# --- inactivity ----------------------------------------------------------


def test_inactivity_closes_a_window_early() -> None:
    """A two-minute gap ends the burst; the window before it closes on inactivity."""
    first = stream(4, step=1.0)
    second = stream(3, step=1.0, start=EPOCH + timedelta(minutes=2))

    windows = window_flows(first + second, size=50, inactivity=timedelta(seconds=30))

    assert bounds(windows) == [(4, 0), (3, 1)]
    assert windows[0].trigger is WindowTrigger.INACTIVITY
    assert windows[1].trigger is WindowTrigger.END_OF_STREAM


def test_no_window_spans_an_inactivity_gap() -> None:
    first = stream(4, step=1.0)
    second = stream(4, step=1.0, start=EPOCH + timedelta(minutes=5))

    windows = window_flows(first + second, size=50, inactivity=timedelta(seconds=30))

    for window in windows:
        spans = [
            later.timestamp - earlier.timestamp
            for earlier, later in zip(window.records, window.records[1:], strict=False)
        ]
        assert all(gap <= timedelta(seconds=30) for gap in spans), window.key


def test_inactivity_is_not_triggered_by_the_threshold_itself() -> None:
    """A gap exactly equal to the threshold is still one burst."""
    flows = stream(4, step=30.0)

    windows = window_flows(flows, size=50, inactivity=timedelta(seconds=30))

    assert len(windows) == 1


# --- D-013: which entity a window is keyed on ----------------------------


def test_a_flood_is_invisible_per_source_and_obvious_per_destination() -> None:
    """The evidence behind D-013, measured rather than argued."""
    flows = generate_flows(GenerationSpec(Scenario.DDOS, 40, 7))
    assert len({str(record.dst_ip) for record in flows}) == 1

    per_source = window_flows(flows, size=20, key=WindowKey.SOURCE)
    per_destination = window_flows(flows, size=20, key=WindowKey.DESTINATION)

    assert len(per_source) > 30, "one window per attacker"
    assert all(len(window.records) == 1 for window in per_source)
    assert bounds(per_destination) == [(20, 0), (20, 1)]


def test_destination_keyed_windows_are_scorable() -> None:
    """A destination window holds many sources and must still extract cleanly."""
    flows = generate_flows(GenerationSpec(Scenario.DDOS, 40, 7))
    (window,) = window_flows(flows, size=40, key=WindowKey.DESTINATION)

    rows = extract_flow_window(window.records, key=WindowKey.DESTINATION)

    assert len(rows) == 40
    assert rows[0].entity == window.key
    with pytest.raises(ValueError, match="exactly one source entity"):
        extract_flow_window(window.records)


def test_flow_key_follows_the_requested_dimension() -> None:
    (record,) = stream(1)

    assert flow_key(record, WindowKey.SOURCE) == "10.4.20.11"
    assert flow_key(record, WindowKey.DESTINATION) == "10.4.20.12"


# --- logs ----------------------------------------------------------------


def test_log_windows_are_keyed_on_host_and_service() -> None:
    logs = generate_logs(GenerationSpec(Scenario.INSIDER_THREAT, 10, 3))

    windows = window_logs(logs, size=200)

    assert sorted(window.key for window in windows) == [
        "10.4.20.12|api-gateway",
        "10.4.20.12|auditd",
        "10.4.20.12|sshd",
        "10.4.20.12|sudo",
    ]
    assert all(window.key_kind == "host+service" for window in windows)
    assert sorted(len(window.records) for window in windows) == [2, 2, 2, 4]
    (sudo,) = [window for window in windows if window.key == "10.4.20.12|sudo"]
    assert {record.level for record in sudo.records} == {LogLevel.WARNING}


def test_log_key_composes_host_and_service() -> None:
    line = LogRecord(
        timestamp=EPOCH,
        host="10.4.20.12",
        service="sudo",
        level=LogLevel.WARNING,
        message="x",
    )

    assert log_key(line) == "10.4.20.12|sudo"


# --- validation ----------------------------------------------------------


def test_an_empty_stream_has_no_windows() -> None:
    """An empty stream is legitimate; it is not an error."""
    assert window_flows([]) == ()
    assert window_logs([]) == ()


def test_configuration_is_validated() -> None:
    with pytest.raises(ValueError, match="window size must be positive"):
        window_flows(stream(2), size=0)

    with pytest.raises(ValueError, match="stride must be positive"):
        window_flows(stream(2), size=5, stride=0)

    with pytest.raises(ValueError, match="would drop records"):
        window_flows(stream(2), size=5, stride=6)


def test_an_unordered_stream_is_refused() -> None:
    flows = stream(4)
    shuffled = [flows[0], flows[2], flows[1], flows[3]]

    with pytest.raises(ValueError, match="arrival order"):
        window_flows(shuffled, size=2)


# --- integration ---------------------------------------------------------


def test_windowing_then_extraction_runs_over_a_whole_synthetic_stream() -> None:
    """The pipeline end to end: no window may be rejected by the extractor."""
    flows = generate_flows(GenerationSpec(Scenario.NORMAL, 200, 7))

    windows = window_flows(flows, size=50)
    rows = [row for window in windows for row in extract_flow_window(window.records)]

    assert len(windows) >= 4
    assert len(rows) == sum(len(window.records) for window in windows)
    assert all(len(window.records) == 50 for window in windows if window.is_complete)
