"""The drift monitor's observed distributions must read the fields ingest stores.

Regression: `proto` was read from the legacy key only. Ingested flow@1 records name the
field `protocol`, so every flow counted as TCP, and PSI for the protocol feature was
measured against a distribution that never occurred (3.75 on a live system).
"""

from __future__ import annotations

from app.services.drift_monitor import _compute_distribution


def test_protocol_is_read_from_flow_v1_field() -> None:
    flows = [{"protocol": "udp"}, {"protocol": "udp"}, {"protocol": "tcp"}]
    dist = _compute_distribution(flows, "proto")
    assert dist == {"udp": 2 / 3, "tcp": 1 / 3}


def test_legacy_proto_key_still_read() -> None:
    flows = [{"proto": "icmp"}, {"proto": "icmp"}]
    assert _compute_distribution(flows, "proto") == {"icmp": 1.0}


def test_flow_v1_wins_when_both_present() -> None:
    assert _compute_distribution([{"protocol": "udp", "proto": "tcp"}], "proto") == {"udp": 1.0}


def test_destination_port_buckets_unknown_ports_as_other() -> None:
    flows = [{"dst_port": 443}, {"dst_port": 8080}]
    assert _compute_distribution(flows, "dst_port") == {"443": 0.5, "other": 0.5}
