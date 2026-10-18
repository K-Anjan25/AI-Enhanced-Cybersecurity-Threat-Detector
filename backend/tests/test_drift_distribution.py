"""The drift monitor's observed distributions must read the fields ingest stores.

Regression: `proto` was read from the legacy key only. Ingested flow@1 records name the
field `protocol`, so every flow counted as TCP, and PSI for the protocol feature was
measured against a distribution that never occurred (3.75 on a live system).
"""

from __future__ import annotations

import pytest
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


def test_measured_baselines_are_distributions_and_self_consistent() -> None:
    """The dst_port and proto baselines are measured references (see drift_monitor).

    Each must be a probability distribution, and a sample drawn exactly from the
    reference must score a PSI near zero. A typo in a value fails here, not in the
    dashboard.
    """
    from app.services.drift_monitor import FEATURE_BASELINES, _compute_psi

    for feature in ("dst_port", "proto"):
        baseline = FEATURE_BASELINES[feature]
        assert abs(sum(baseline.values()) - 1.0) < 1e-3, feature
        assert all(value > 0 for value in baseline.values()), feature
        assert _compute_psi(baseline, dict(baseline)) == pytest.approx(0.0, abs=1e-9)
