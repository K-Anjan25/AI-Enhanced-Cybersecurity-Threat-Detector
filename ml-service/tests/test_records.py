"""Tests for the flow@1 and log@1 record contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from ipaddress import IPv4Address

import pytest
from aegis_ml.data.records import (
    SCHEMA_VERSION_FLOW,
    Direction,
    FlowRecord,
    LogLevel,
    LogRecord,
    Protocol,
)
from pydantic import ValidationError


def make_flow(**overrides: object) -> FlowRecord:
    base: dict[str, object] = {
        "timestamp": datetime(2026, 1, 5, 8, 0, tzinfo=UTC),
        "src_ip": IPv4Address("10.4.20.11"),
        "dst_ip": IPv4Address("45.83.2.11"),
        "src_port": 51234,
        "dst_port": 443,
        "protocol": Protocol.TCP,
        "direction": Direction.OUTBOUND,
        "packets": 12,
        "src_packets": 6,
        "dst_packets": 6,
        "src_bytes": 900,
        "dst_bytes": 4200,
        "duration": 1.25,
    }
    base.update(overrides)
    return FlowRecord(**base)


def test_schema_version_is_pinned() -> None:
    """The version is a literal, so a record cannot claim to be flow@1 falsely."""
    assert make_flow().schema_version == "flow@1"
    assert SCHEMA_VERSION_FLOW == "flow@1"


def test_naive_timestamp_is_rejected() -> None:
    """A naive timestamp would silently corrupt window boundaries (R-30)."""
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_flow(timestamp=datetime(2026, 1, 5, 8, 0))


def test_timestamp_is_normalised_to_utc() -> None:
    """A non-UTC offset is converted, not merely accepted."""
    offset = timezone(timedelta(hours=5, minutes=30))
    record = make_flow(timestamp=datetime(2026, 1, 5, 13, 30, tzinfo=offset))

    assert record.timestamp.tzinfo is UTC
    assert record.timestamp == datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


def test_unknown_fields_are_rejected() -> None:
    """extra='forbid' stops a typo'd field from being silently dropped (FR-04)."""
    with pytest.raises(ValidationError, match="dst_portt"):
        make_flow(dst_portt=80)


def test_port_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_flow(dst_port=70000)


def test_negative_counters_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_flow(src_bytes=-1)


def test_records_are_immutable() -> None:
    """frozen=True keeps a record from being mutated after it is stored."""
    record = make_flow()

    with pytest.raises(ValidationError):
        record.dst_port = 80  # type: ignore[misc]


def test_label_is_optional_for_live_traffic() -> None:
    """Live traffic is unlabelled by definition."""
    assert make_flow().label is None
    assert make_flow(label="Reconnaissance").label == "Reconnaissance"


def test_ip_strings_are_parsed_to_addresses() -> None:
    record = make_flow(src_ip="10.4.20.99")

    assert record.src_ip == IPv4Address("10.4.20.99")


def test_log_record_requires_a_non_empty_message() -> None:
    with pytest.raises(ValidationError):
        LogRecord(
            timestamp=datetime(2026, 1, 5, 8, 0, tzinfo=UTC),
            host="web-07",
            service="sshd",
            level=LogLevel.INFO,
            message="",
        )


def test_log_record_defaults_template_fields_to_empty() -> None:
    record = LogRecord(
        timestamp=datetime(2026, 1, 5, 8, 0, tzinfo=UTC),
        host="web-07",
        service="sshd",
        level=LogLevel.WARNING,
        message="Failed password for j.rivera",
    )

    assert record.template_id is None
    assert record.parameters == {}
