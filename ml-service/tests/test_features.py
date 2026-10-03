"""Tests for `features@1` extraction (T-107).

The golden hash below is the point of this file: it is what makes "a
feature-definition change requires a version bump" a build failure rather than
an intention.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from aegis_ml.data.features import (
    CATEGORICAL_FEATURES,
    DERIVED_FEATURES,
    FEATURE_NAMES,
    FEATURES_SCHEMA_HASH,
    FEATURES_SCHEMA_VERSION,
    FLAG_FEATURES,
    LOG_FEATURE_NAMES,
    MISSING,
    NUMERIC_FEATURES,
    TIMING_FEATURES,
    VOLUME_FEATURES,
    extract_flow_window,
    extract_log_window,
    schema_hash,
)
from aegis_ml.data.records import Direction, FlowRecord, LogLevel, LogRecord, Protocol
from aegis_ml.data.synthetic import GenerationSpec, Scenario, generate_flows, generate_logs

#: Golden digest. Update this AND FEATURES_SCHEMA_VERSION together, never alone.
EXPECTED_HASH = "3b9fa1af3b5644dcde52081944af2ae77df34b12e69c9acc1a4787bdc85367dd"

EPOCH = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


def flow(
    *,
    offset: float = 0.0,
    src: str = "10.4.20.11",
    dst: str = "10.4.20.12",
    dst_port: int = 80,
    src_bytes: int = 1200,
    dst_bytes: int = 3400,
    packets: int = 10,
    src_packets: int = 5,
    dst_packets: int = 5,
    duration: float = 0.8,
    label: str | None = "normal",
    service: str | None = "http",
    state: str | None = "SF",
) -> FlowRecord:
    """Build a valid ``flow@1`` record with only the interesting fields varied."""
    return FlowRecord(
        timestamp=EPOCH + timedelta(seconds=offset),
        src_ip=src,
        dst_ip=dst,
        src_port=51000,
        dst_port=dst_port,
        protocol=Protocol.TCP,
        direction=Direction.INTERNAL,
        service=service,
        state=state,
        packets=packets,
        src_packets=src_packets,
        dst_packets=dst_packets,
        src_bytes=src_bytes,
        dst_bytes=dst_bytes,
        duration=duration,
        label=label,
    )


def log(
    *,
    offset: float = 0.0,
    host: str = "10.4.20.12",
    service: str = "sshd",
    level: LogLevel = LogLevel.INFO,
    template_id: str | None = None,
    parameters: dict[str, str] | None = None,
    label: str | None = "BruteForce",
) -> LogRecord:
    """Build a valid ``log@1`` record."""
    return LogRecord(
        timestamp=EPOCH + timedelta(seconds=offset),
        host=host,
        service=service,
        level=level,
        message="Failed password for j.rivera",
        template_id=template_id,
        parameters=parameters if parameters is not None else {},
        label=label,
    )


# --- the schema contract -------------------------------------------------


def test_schema_hash_is_pinned() -> None:
    """A feature change without a version bump must fail here."""
    assert FEATURES_SCHEMA_VERSION == "features@1"
    assert schema_hash() == EXPECTED_HASH
    assert FEATURES_SCHEMA_HASH == EXPECTED_HASH


def test_feature_list_matches_the_documented_groups() -> None:
    """architecture.md 7.1 defines five groups; the counts are asserted, not trusted.

    The document used to claim 24 features while listing 23. The table is the
    specification, so 23 is the contract and the prose was corrected.
    """
    assert len(VOLUME_FEATURES) == 5
    assert len(TIMING_FEATURES) == 3
    assert len(FLAG_FEATURES) == 6
    assert len(DERIVED_FEATURES) == 5
    assert len(CATEGORICAL_FEATURES) == 4
    assert len(NUMERIC_FEATURES) == 19
    assert len(FEATURE_NAMES) == 23
    assert FEATURE_NAMES == CATEGORICAL_FEATURES + NUMERIC_FEATURES
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES), "feature names must be unique"


def test_rows_align_with_the_name_tuples() -> None:
    (row,) = extract_flow_window([flow()])

    assert len(row.categorical) == len(CATEGORICAL_FEATURES)
    assert len(row.numeric) == len(NUMERIC_FEATURES)
    assert set(row.as_dict()) == set(FEATURE_NAMES) | {"label"}
    assert row.schema_version == "features@1"
    assert row.entity == "10.4.20.11"


def test_log_feature_names_align() -> None:
    (row,) = extract_log_window([log()])

    assert len(LOG_FEATURE_NAMES) == 3
    assert len(row.numeric) == len(LOG_FEATURE_NAMES)
    assert set(row.as_dict()) == set(LOG_FEATURE_NAMES) | {"template_id", "label"}


# --- values, hand-computed ----------------------------------------------


def test_hand_computed_values() -> None:
    """Two flows, ten seconds apart, two distinct ports — every value is checkable."""
    a = flow(offset=0.0, dst_port=80, src_bytes=60, dst_bytes=0, src_packets=3, dst_packets=0)
    b = flow(offset=10.0, dst_port=443, src_bytes=500, dst_bytes=1500, src_packets=5, dst_packets=7)

    ra, rb = extract_flow_window([a, b])
    va, vb = ra.as_dict(), rb.as_dict()

    assert va["inter_arrival_mean"] == 10.0
    assert va["inter_arrival_std"] == 0.0, "one gap has no spread"
    assert va["port_entropy"] == pytest.approx(1.0), "two equally likely ports = 1 bit"
    assert va["dst_port_count"] == 2.0
    assert va["dst_ip_count"] == 1.0
    assert va["byte_ratio"] == pytest.approx(61.0), "Laplace-smoothed: 61 / 1"
    assert va["packet_ratio"] == pytest.approx(4.0)
    assert vb["byte_ratio"] == pytest.approx(501.0 / 1501.0)
    assert vb["packet_ratio"] == pytest.approx(6.0 / 8.0)
    assert va["protocol"] == "tcp"
    assert va["direction"] == "internal"
    assert va["service"] == "http"
    assert va["state"] == "SF"


def test_ratios_stay_finite_when_the_reply_is_empty() -> None:
    """Port scans have zero reply bytes; the feature must not go infinite or NaN."""
    (row,) = extract_flow_window([flow(dst_bytes=0, dst_packets=0)])

    assert math.isfinite(row.numeric_value("byte_ratio"))
    assert math.isfinite(row.numeric_value("packet_ratio"))
    assert row.numeric_value("byte_ratio") > 1.0


def test_entropy_separates_a_sweep_from_a_single_port() -> None:
    single = extract_flow_window([flow(dst_port=80, offset=float(i)) for i in range(8)])
    sweep = extract_flow_window([flow(dst_port=1024 + i, offset=float(i)) for i in range(8)])

    assert single[0].numeric_value("port_entropy") == 0.0
    assert single[0].numeric_value("dst_port_count") == 1.0
    assert sweep[0].numeric_value("port_entropy") == pytest.approx(math.log2(8))
    assert sweep[0].numeric_value("dst_port_count") == 8.0


def test_inter_arrival_statistics_track_jitter() -> None:
    steady = extract_flow_window([flow(offset=i * 10.0) for i in range(5)])
    erratic = extract_flow_window([flow(offset=o) for o in (0.0, 1.0, 40.0, 41.0, 200.0)])

    assert steady[0].numeric_value("inter_arrival_std") == 0.0
    assert steady[0].numeric_value("inter_arrival_mean") == 10.0
    assert erratic[0].numeric_value("inter_arrival_std") > 60.0


def test_missing_optional_fields_become_a_distinct_sentinel() -> None:
    """Null must not collapse into an empty string or a zero embedding."""
    (row,) = extract_flow_window([flow(service=None, state=None)])

    assert row.categorical_value("service") == MISSING
    assert row.categorical_value("state") == MISSING
    assert MISSING == "unknown"


# --- labels and validation ----------------------------------------------


def test_label_is_kept_only_when_the_window_agrees() -> None:
    pure = extract_flow_window([flow(label="DoS"), flow(offset=1.0, label="DoS")])
    mixed = extract_flow_window([flow(label="DoS"), flow(offset=1.0, label="normal")])
    unlabelled = extract_flow_window([flow(label=None)])

    assert pure[0].label == "DoS"
    assert mixed[0].label is None, "an ambiguous window must not assert a label"
    assert unlabelled[0].label is None


def test_windows_are_validated() -> None:
    with pytest.raises(ValueError, match="empty window"):
        extract_flow_window([])

    with pytest.raises(ValueError, match="exactly one source entity"):
        extract_flow_window([flow(src="10.4.20.11"), flow(offset=1.0, src="10.4.20.12")])

    with pytest.raises(ValueError, match="ordered by arrival time"):
        extract_flow_window([flow(offset=10.0), flow(offset=0.0)])

    with pytest.raises(ValueError, match="empty window"):
        extract_log_window([])

    with pytest.raises(ValueError, match="exactly one host\\+service"):
        extract_log_window([log(service="sshd"), log(offset=1.0, service="sudo")])

    with pytest.raises(ValueError, match="ordered by time"):
        extract_log_window([log(offset=10.0), log(offset=0.0)])


def test_extraction_is_reproducible() -> None:
    """Same input, same rows — asserted on synthetic data end to end."""
    spec = GenerationSpec(scenario=Scenario.BEACONING, count=50, seed=7)
    first = extract_flow_window(generate_flows(spec))
    second = extract_flow_window(generate_flows(spec))

    assert first == second
    assert len(first) == 50


def test_features_are_derivable_from_raw_records() -> None:
    """The acceptance criterion for T-107: the matrix is a pure function of the input."""
    spec = GenerationSpec(scenario=Scenario.PORT_SCAN, count=50, seed=7)
    flows = generate_flows(spec)

    rows = extract_flow_window(flows)

    assert rows[0].numeric_value("dst_port_count") == 50.0
    assert rows[0].numeric_value("port_entropy") == pytest.approx(math.log2(50))
    assert rows[0].numeric_value("dst_ip_count") == 1.0
    assert rows[0].label == "Reconnaissance"
    # Half-open SYNs with no reply: the byte ratio is dominated by the request.
    assert all(row.numeric_value("byte_ratio") > 50.0 for row in rows)


def by_entity(flows: Sequence[FlowRecord]) -> dict[str, list[FlowRecord]]:
    """Group generated flows by source entity — the unit a window is built over.

    The generator emits multi-entity traffic on purpose: ordinary browsing comes
    from several hosts at once, so windowing has to partition before extracting.
    """
    groups: dict[str, list[FlowRecord]] = {}
    for record in flows:
        groups.setdefault(str(record.src_ip), []).append(record)
    return groups


def test_beaconing_is_visible_as_collapsed_inter_arrival_spread() -> None:
    """The feature that must separate T6 from ordinary browsing (measured, not guessed)."""
    beacon = extract_flow_window(generate_flows(GenerationSpec(Scenario.BEACONING, 50, 7)))
    normal_stds = [
        extract_flow_window(group)[0].numeric_value("inter_arrival_std")
        for group in by_entity(generate_flows(GenerationSpec(Scenario.NORMAL, 50, 7))).values()
    ]

    assert beacon[0].numeric_value("inter_arrival_std") == pytest.approx(0.1381, abs=1e-3)
    assert min(normal_stds) > 2.0, "ordinary browsing must be visibly jitterier"
    assert beacon[0].numeric_value("port_entropy") == 0.0


def test_window_extraction_requires_partitioning_by_entity() -> None:
    """A raw multi-entity stream is refused rather than silently mixed."""
    flows = generate_flows(GenerationSpec(Scenario.NORMAL, 50, 7))

    assert len(by_entity(flows)) > 1
    with pytest.raises(ValueError, match="exactly one source entity"):
        extract_flow_window(flows)


@pytest.mark.parametrize("scenario", list(Scenario))
def test_every_scenario_generates_an_ordered_timeline(scenario: Scenario) -> None:
    """Regression guard: `index * rng.uniform(a, b)` used to run time backwards.

    Three builders (normal, exfiltration, insider_threat) did this, and nothing
    caught it until windowing started asserting arrival order.
    """
    flows = generate_flows(GenerationSpec(scenario, 40, 7))
    stamps = [record.timestamp for record in flows]

    assert stamps == sorted(stamps), f"{scenario.value} generated an out-of-order timeline"


# --- log side ------------------------------------------------------------


def test_log_features_encode_severity_and_template_state() -> None:
    rows = extract_log_window(
        [
            log(offset=0.0, level=LogLevel.DEBUG, template_id="T1", parameters={"a": "1"}),
            log(offset=1.0, level=LogLevel.CRITICAL, parameters={"a": "1", "b": "2"}),
        ]
    )

    assert rows[0].numeric_value("level_ordinal") == 0.0
    assert rows[1].numeric_value("level_ordinal") == 4.0
    assert rows[0].numeric_value("parameter_count") == 1.0
    assert rows[1].numeric_value("parameter_count") == 2.0
    assert rows[0].numeric_value("template_known") == 1.0
    assert rows[1].numeric_value("template_known") == 0.0
    assert rows[0].template_id == "T1"
    assert rows[1].template_id is None
    assert rows[0].label == "BruteForce"


def test_log_extraction_runs_on_generated_insider_logs() -> None:
    """The insider stream spans four host+service pairs, so it must be grouped first."""
    spec = GenerationSpec(scenario=Scenario.INSIDER_THREAT, count=10, seed=3)
    groups: dict[tuple[str, str], list[LogRecord]] = {}
    for line in generate_logs(spec):
        groups.setdefault((line.host, line.service), []).append(line)

    assert set(groups) == {
        ("10.4.20.12", "sshd"),
        ("10.4.20.12", "sudo"),
        ("10.4.20.12", "auditd"),
        ("10.4.20.12", "api-gateway"),
    }

    rows = [row for group in groups.values() for row in extract_log_window(group)]

    assert len(rows) == 10
    assert {row.label for row in rows} == {"InsiderThreat"}
    assert max(row.numeric_value("level_ordinal") for row in rows) == 3.0, "error, not critical"
    # The sudo group carries the privilege-escalation evidence.
    sudo = extract_log_window(groups[("10.4.20.12", "sudo")])
    assert len(sudo) == 4
