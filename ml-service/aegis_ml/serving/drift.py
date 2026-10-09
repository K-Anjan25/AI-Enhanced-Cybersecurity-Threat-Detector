"""Drift detection endpoint for the ML service.

Computes Population Stability Index (PSI) for flow features
to detect when traffic patterns diverge from the baseline.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["drift"])

# PSI thresholds
PSI_STABLE = 0.10
PSI_MODERATE = 0.25
PSI_DRIFT_THRESHOLD = 0.25

# Feature baselines (from typical network traffic)
FEATURE_BASELINES: dict[str, dict[str, float]] = {
    "dst_port": {
        "80": 0.25,
        "443": 0.35,
        "53": 0.15,
        "22": 0.05,
        "3389": 0.02,
        "25": 0.03,
        "993": 0.03,
        "587": 0.02,
        "other": 0.10,
    },
    "proto": {"tcp": 0.70, "udp": 0.25, "icmp": 0.05},
    "duration_bucket": {
        "0-1s": 0.40,
        "1-10s": 0.25,
        "10-60s": 0.15,
        "1-5m": 0.10,
        "5m+": 0.10,
    },
}


class FlowRecord(BaseModel):
    """A flow record for drift analysis."""

    ts: float = 0
    src_ip: str = ""
    dst_ip: str = ""
    src_port: int = 0
    dst_port: int = 0
    proto: str = "tcp"
    service: str | None = None
    duration: float | None = None
    orig_bytes: int = 0
    resp_bytes: int = 0
    conn_state: str | None = None


class DriftRequest(BaseModel):
    """Flows to check for drift."""

    flows: list[FlowRecord] = Field(..., min_length=1)
    window_id: str | None = None


class DriftResult(BaseModel):
    """PSI score for one feature."""

    feature: str
    psi: float
    status: str  # "stable", "moderate", "drifted"
    details: dict[str, Any] = {}


class DriftResponse(BaseModel):
    """Drift detection results."""

    overall_status: str
    features: list[DriftResult]
    window_id: str | None = None
    flow_count: int


def compute_psi(expected: dict[str, float], observed: dict[str, float]) -> float:
    """Compute Population Stability Index.

    PSI = Σ (actual_i - expected_i) * ln(actual_i / expected_i)

    Args:
        expected: baseline distribution (proportions summing to ~1)
        observed: current distribution (proportions summing to ~1)

    Returns:
        PSI value. < 0.10 = stable, 0.10-0.25 = moderate, > 0.25 = drifted.
    """
    epsilon = 1e-6
    all_keys = set(expected.keys()) | set(observed.keys())

    psi = 0.0
    for key in all_keys:
        e = max(expected.get(key, 0), epsilon)
        o = max(observed.get(key, 0), epsilon)
        psi += (o - e) * math.log(o / e)

    return psi


def bucket_port(port: int) -> str:
    """Bucket a port number into common categories."""
    common = {
        80: "80",
        443: "443",
        53: "53",
        22: "22",
        3389: "3389",
        25: "25",
        993: "993",
        587: "587",
    }
    return common.get(port, "other")


def bucket_duration(duration: float | None) -> str:
    """Bucket a duration into ranges."""
    if duration is None:
        return "0-1s"
    if duration < 1:
        return "0-1s"
    if duration < 10:
        return "1-10s"
    if duration < 60:
        return "10-60s"
    if duration < 300:
        return "1-5m"
    return "5m+"


def compute_feature_distribution(flows: list[FlowRecord], feature: str) -> dict[str, float]:
    """Compute the distribution of a feature from flows."""
    total = len(flows)
    if total == 0:
        return {}

    counter: Counter[str] = Counter()
    for f in flows:
        if feature == "dst_port":
            counter[bucket_port(f.dst_port)] += 1
        elif feature == "proto":
            counter[f.proto] += 1
        elif feature == "duration_bucket":
            counter[bucket_duration(f.duration)] += 1

    return {k: v / total for k, v in counter.items()}


@router.post(
    "/drift",
    response_model=DriftResponse,
    summary="Check for feature drift in flow window",
)
def detect_drift(request: DriftRequest) -> DriftResponse:
    """Compute PSI for each feature against baseline distributions.

    Drift indicates that current traffic patterns differ significantly
    from the training baseline, which may mean:
    - Model performance is degrading
    - Network behavior has changed
    - New types of traffic are appearing
    """
    flows = request.flows
    results: list[DriftResult] = []

    for feature, baseline in FEATURE_BASELINES.items():
        observed = compute_feature_distribution(flows, feature)
        if not observed:
            continue

        psi = compute_psi(baseline, observed)

        if psi < PSI_STABLE:
            status = "stable"
        elif psi < PSI_MODERATE:
            status = "moderate"
        else:
            status = "drifted"

        results.append(
            DriftResult(
                feature=feature,
                psi=round(psi, 4),
                status=status,
                details={
                    "baseline": baseline,
                    "observed": observed,
                },
            )
        )

    # Overall status is the worst individual status
    if any(r.status == "drifted" for r in results):
        overall = "drifted"
    elif any(r.status == "moderate" for r in results):
        overall = "moderate"
    else:
        overall = "stable"

    return DriftResponse(
        overall_status=overall,
        features=results,
        window_id=request.window_id,
        flow_count=len(flows),
    )
