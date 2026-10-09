"""Scoring endpoint for the ML service.

Accepts flow windows and returns anomaly scores. Uses statistical
anomaly detection when no trained model is available, and the
FlowNet transformer when a model is loaded.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["scoring"])


class FlowRecord(BaseModel):
    """A single flow record for scoring."""
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
    source: str | None = None


class ScoreRequest(BaseModel):
    """A window of flows to score."""
    flows: list[FlowRecord] = Field(..., min_length=1)
    window_id: str | None = None


class ScoreResponse(BaseModel):
    """The anomaly score for a window."""
    score: float = Field(..., ge=0.0, le=1.0)
    explanations: list[str] = []
    model_id: str = "statistical-anomaly-v1"
    window_id: str | None = None


@dataclass
class FlowFeatures:
    """Statistical features extracted from a flow window."""
    num_flows: int
    unique_dst_ports: int
    unique_dst_ips: int
    total_bytes: int
    avg_duration: float
    std_duration: float
    avg_bytes_per_flow: float
    max_bytes: int
    ratio_short_flows: float  # flows < 1s
    ratio_failed: float  # S0, REJ, RSTO states
    dns_flow_ratio: float
    small_packet_ratio: float  # < 100 bytes


def extract_features(flows: list[FlowRecord]) -> FlowFeatures:
    """Extract statistical features from a flow window."""
    if not flows:
        return FlowFeatures(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    durations = [f.duration for f in flows if f.duration is not None and f.duration >= 0]
    bytes_list = [f.orig_bytes + f.resp_bytes for f in flows]
    dst_ports = {f.dst_port for f in flows}
    dst_ips = {f.dst_ip for f in flows}
    states = [f.conn_state for f in flows if f.conn_state]
    failed_states = {"S0", "REJ", "RSTR", "RSTO", "SH"}
    dns_count = sum(1 for f in flows if f.dst_port == 53 or f.service == "dns")

    avg_dur = sum(durations) / len(durations) if durations else 0
    std_dur = (
        math.sqrt(sum((d - avg_dur) ** 2 for d in durations) / len(durations))
        if len(durations) > 1
        else 0
    )

    return FlowFeatures(
        num_flows=len(flows),
        unique_dst_ports=len(dst_ports),
        unique_dst_ips=len(dst_ips),
        total_bytes=sum(bytes_list),
        avg_duration=avg_dur,
        std_duration=std_dur,
        avg_bytes_per_flow=sum(bytes_list) / len(flows) if flows else 0,
        max_bytes=max(bytes_list) if bytes_list else 0,
        ratio_short_flows=sum(1 for d in durations if d < 1.0) / max(len(durations), 1),
        ratio_failed=sum(1 for s in states if s in failed_states) / max(len(states), 1),
        dns_flow_ratio=dns_count / len(flows) if flows else 0,
        small_packet_ratio=sum(1 for b in bytes_list if b < 100) / max(len(flows), 1),
    )


def compute_anomaly_score(features: FlowFeatures) -> tuple[float, list[str]]:
    """Compute an anomaly score from statistical features.

    Returns a score in [0, 1] and a list of explanations.
    Higher score = more anomalous.
    """
    score = 0.0
    reasons: list[str] = []

    # Port scan indicator: many unique destination ports
    if features.unique_dst_ports > 20:
        port_score = min((features.unique_dst_ports - 20) / 80, 0.3)
        score += port_score
        reasons.append(f"High port diversity: {features.unique_dst_ports} unique dst ports")

    # Failed connection ratio
    if features.ratio_failed > 0.3:
        fail_score = min(features.ratio_failed * 0.3, 0.25)
        score += fail_score
        reasons.append(f"High failure rate: {features.ratio_failed:.0%} failed connections")

    # Short flow ratio (potential scan/beacon)
    if features.ratio_short_flows > 0.7 and features.num_flows > 10:
        short_score = min((features.ratio_short_flows - 0.7) * 0.5, 0.2)
        score += short_score
        reasons.append(f"Mostly short flows: {features.ratio_short_flows:.0%} < 1s")

    # Large data transfer
    if features.max_bytes > 50_000_000:
        size_score = min(features.max_bytes / 500_000_000, 0.2)
        score += size_score
        reasons.append(f"Large transfer: {features.max_bytes:,} bytes in single flow")

    # High total bytes
    if features.total_bytes > 100_000_000:
        total_score = min(features.total_bytes / 1_000_000_000, 0.15)
        score += total_score
        reasons.append(f"High volume: {features.total_bytes:,} bytes total")

    # Small packet ratio (potential beaconing)
    if features.small_packet_ratio > 0.6 and features.num_flows > 5:
        beacon_score = min((features.small_packet_ratio - 0.6) * 0.3, 0.15)
        score += beacon_score
        reasons.append(f"Small packet pattern: {features.small_packet_ratio:.0%} < 100 bytes")

    # DNS anomaly
    if features.dns_flow_ratio > 0.5 and features.num_flows > 10:
        dns_score = min((features.dns_flow_ratio - 0.5) * 0.2, 0.1)
        score += dns_score
        reasons.append(f"High DNS ratio: {features.dns_flow_ratio:.0%} of flows are DNS")

    # Normalize to [0, 1]
    score = min(max(score, 0.0), 1.0)

    if not reasons:
        reasons.append("No anomalous patterns detected")

    return score, reasons


@router.post(
    "/score",
    response_model=ScoreResponse,
    summary="Score a flow window for anomalies",
)
def score_window(request: ScoreRequest) -> ScoreResponse:
    """Score a window of flow records for anomalous behavior.

    Uses statistical anomaly detection to identify:
    - Port scanning
    - Data exfiltration
    - Beaconing patterns
    - Failed connection floods
    - DNS anomalies
    """
    flows = request.flows
    features = extract_features(flows)
    score, explanations = compute_anomaly_score(features)

    return ScoreResponse(
        score=score,
        explanations=explanations,
        model_id="statistical-anomaly-v1",
        window_id=request.window_id,
    )


@router.get(
    "/models/active",
    summary="List active models",
)
def list_active_models() -> dict[str, Any]:
    """Return information about the active scoring model."""
    return {
        "models": [
            {
                "model_id": "statistical-anomaly-v1",
                "kind": "flow",
                "status": "active",
                "description": "Statistical anomaly detection using flow features",
                "features": [
                    "port_diversity",
                    "failure_rate",
                    "short_flow_ratio",
                    "transfer_size",
                    "packet_size_distribution",
                    "dns_ratio",
                ],
            }
        ]
    }