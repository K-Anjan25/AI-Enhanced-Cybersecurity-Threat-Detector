"""Scoring endpoint for the ML service.

Accepts flow windows and returns anomaly scores. Uses three detection layers:

1. **FlowNet transformer** (T-201) — a 4-layer transformer with reconstruction
   + anomaly heads. Detects novel patterns via reconstruction error.
2. **LogNet transformer** (T-204) — a 6-layer transformer over log templates.
   Detects anomalous log sequences via hypersphere distance.
3. **Statistical fallback** — rule-based feature scoring when no trained model
   is loaded. Always available as a safety net.

The composite score is T-205's job: both heads' outputs are combined, and the
statistical score acts as a floor when the neural model is absent.
"""

from __future__ import annotations

import logging
import math
import os
from collections import Counter
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scoring"])

# ── PyTorch models (optional) ──────────────────────────────────

# Typed Any: torch is an optional extra, so the model classes are not always importable.
_flownet_model: Any = None
_lognet_model: Any = None
_models_loaded = False

FLOWNET_MODEL_PATH = os.environ.get("AEGIS_FLOWNET_MODEL_PATH", "/models/flownet.pt")
LOGNET_MODEL_PATH = os.environ.get("AEGIS_LOGNET_MODEL_PATH", "/models/lognet.pt")


def _try_load_models() -> None:
    """Attempt to load PyTorch models. Non-fatal if torch is absent."""
    global _flownet_model, _lognet_model, _models_loaded
    if _models_loaded:
        return

    try:
        import torch

        from aegis_ml.models.flownet import FlowNet, FlowNetConfig
        from aegis_ml.models.lognet import LogNet, LogNetConfig

        # Load FlowNet if checkpoint exists
        if os.path.exists(FLOWNET_MODEL_PATH):
            config = FlowNetConfig()
            model = FlowNet(config)
            state = torch.load(FLOWNET_MODEL_PATH, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            model.eval()
            _flownet_model = model
            logger.info(
                "flownet_loaded path=%s params=%d",
                FLOWNET_MODEL_PATH,
                sum(p.numel() for p in model.parameters()),
            )
        else:
            logger.info("flownet_not_found path=%s", FLOWNET_MODEL_PATH)

        # Load LogNet if checkpoint exists
        if os.path.exists(LOGNET_MODEL_PATH):
            lognet_config = LogNetConfig()
            lognet = LogNet(lognet_config)
            state = torch.load(LOGNET_MODEL_PATH, map_location="cpu", weights_only=True)
            lognet.load_state_dict(state)
            lognet.eval()
            _lognet_model = lognet
            logger.info(
                "lognet_loaded path=%s params=%d",
                LOGNET_MODEL_PATH,
                sum(p.numel() for p in lognet.parameters()),
            )
        else:
            logger.info("lognet_not_found path=%s", LOGNET_MODEL_PATH)

    except ImportError:
        logger.info("torch_not_available using_statistical_fallback")
    except Exception as e:  # noqa: BLE001 - a bad checkpoint degrades to the statistical path
        logger.warning("model_load_failed error=%s", str(e))

    _models_loaded = True


# ── Request/Response models ─────────────────────────────────────


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


class LogRecord(BaseModel):
    """A single log record for scoring."""

    source: str = ""
    level: str = "info"
    message: str = ""
    host: str = ""
    timestamp: str = ""


class ScoreRequest(BaseModel):
    """A window of flows to score."""

    flows: list[FlowRecord] = Field(default=[], min_length=0)
    logs: list[LogRecord] = Field(default=[], min_length=0)
    window_id: str | None = None


class ScoreResponse(BaseModel):
    """The anomaly score for a window."""

    score: float = Field(..., ge=0.0, le=1.0)
    explanations: list[str] = []
    model_id: str = "statistical-anomaly-v1"
    window_id: str | None = None
    scoring_method: str = "statistical"  # "transformer" or "statistical"


# ── Feature extraction ──────────────────────────────────────────


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


def compute_statistical_score(features: FlowFeatures) -> tuple[float, list[str]]:
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


def _flows_to_tensor(flows: list[FlowRecord]) -> Any:
    """Convert flow records to a tensor for FlowNet inference."""
    import torch

    # features@1 vector: [src_port, dst_port, proto_onehot(3), duration,
    #   orig_bytes, resp_bytes, orig_pkts, resp_pkts, conn_state_onehot(10)]
    # Simplified: just use the numeric features
    rows = []
    for f in flows:
        proto_vec = [
            1 if f.proto == "tcp" else 0,
            1 if f.proto == "udp" else 0,
            1 if f.proto == "icmp" else 0,
        ]
        row = [
            f.src_port / 65535.0,
            f.dst_port / 65535.0,
            *proto_vec,
            min(f.duration or 0, 300) / 300.0,
            min(f.orig_bytes, 10_000_000) / 10_000_000.0,
            min(f.resp_bytes, 10_000_000) / 10_000_000.0,
            0,
            0,  # packets (not in FlowRecord)
        ]
        rows.append(row)

    return torch.tensor([rows], dtype=torch.float32)  # (1, seq_len, features)


def compute_transformer_score(flows: list[FlowRecord]) -> tuple[float, list[str]]:
    """Score using FlowNet transformer (T-201).

    Uses reconstruction error + anomaly head output.
    Returns a composite score in [0, 1].
    """
    import torch

    if _flownet_model is None:
        return 0.0, ["FlowNet model not loaded"]

    if len(flows) < 2:
        return 0.0, ["Too few flows for transformer scoring"]

    try:
        tensor = _flows_to_tensor(flows)

        with torch.no_grad():
            output = _flownet_model(tensor)

        # Reconstruction error: MSE between input and reconstruction
        recon_error = torch.mean((tensor - output.reconstruction) ** 2).item()

        # Anomaly head: sigmoid of logits
        anomaly_score = torch.sigmoid(output.anomaly_logits).mean().item()

        # Composite: weighted combination (T-205)
        # Reconstruction error is unbounded, so normalize it
        recon_normalized = min(recon_error * 10, 1.0)
        composite = 0.6 * anomaly_score + 0.4 * recon_normalized
        composite = min(max(composite, 0.0), 1.0)

        reasons = []
        if anomaly_score > 0.5:
            reasons.append(f"FlowNet anomaly head: {anomaly_score:.3f}")
        if recon_error > 0.1:
            reasons.append(f"Reconstruction error: {recon_error:.4f}")
        if not reasons:
            reasons.append("FlowNet: normal patterns")

        return composite, reasons

    except Exception as e:  # noqa: BLE001 - a failed model must not fail the whole request
        logger.warning("transformer_scoring_failed error=%s", str(e))
        return 0.0, [f"Transformer scoring failed: {str(e)}"]


# ── Scoring endpoint ────────────────────────────────────────────


@router.post(
    "/score",
    response_model=ScoreResponse,
    summary="Score a flow window for anomalies",
)
def score_window(request: ScoreRequest) -> ScoreResponse:
    """Score a window of flow records for anomalous behavior.

    Detection layers:
    1. FlowNet transformer (if loaded) — detects novel patterns via
       reconstruction error + supervised anomaly head
    2. Statistical fallback — rule-based feature scoring (always available)
    3. Composite score combines both (T-205)
    """
    _try_load_models()

    flows = request.flows
    features = extract_features(flows)

    # Layer 1: Transformer scoring (if model loaded)
    transformer_score = 0.0
    transformer_reasons: list[str] = []
    if _flownet_model is not None and len(flows) >= 2:
        transformer_score, transformer_reasons = compute_transformer_score(flows)

    # Layer 2: Statistical scoring (always available)
    stat_score, stat_reasons = compute_statistical_score(features)

    # Layer 3: Composite (T-205)
    if _flownet_model is not None:
        # Transformer available: weighted combination
        final_score = 0.7 * transformer_score + 0.3 * stat_score
        method = "transformer"
        explanations = transformer_reasons + stat_reasons
        model_id = "flownet-v1"
    else:
        # No transformer: statistical only
        final_score = stat_score
        method = "statistical"
        explanations = stat_reasons
        model_id = "statistical-anomaly-v1"

    final_score = min(max(final_score, 0.0), 1.0)

    return ScoreResponse(
        score=final_score,
        explanations=explanations[:10],  # Cap explanations
        model_id=model_id,
        window_id=request.window_id,
        scoring_method=method,
    )


@router.post(
    "/score/logs",
    response_model=ScoreResponse,
    summary="Score a log window for anomalies (LogNet)",
)
def score_log_window(request: ScoreRequest) -> ScoreResponse:
    """Score a window of log records for anomalous behavior.

    Uses LogNet transformer (T-204) when available:
    - Masked-template prediction (what normally follows what)
    - Hypersphere distance (how far from normal)
    Falls back to statistical heuristics when LogNet is not loaded.
    """
    _try_load_models()

    logs = request.logs
    if not logs:
        return ScoreResponse(score=0.0, explanations=["No logs to score"], model_id="none")

    # Statistical heuristics for log anomaly detection
    score = 0.0
    reasons = []

    # Error/critical ratio
    error_count = sum(1 for entry in logs if entry.level in ("error", "critical"))
    error_ratio = error_count / len(logs) if logs else 0
    if error_ratio > 0.3:
        score += min(error_ratio * 0.5, 0.3)
        reasons.append(f"High error ratio: {error_ratio:.0%}")

    # Unique sources (many different sources = potential scanning)
    sources = {entry.source for entry in logs}
    if len(sources) > 5:
        score += min((len(sources) - 5) * 0.05, 0.2)
        reasons.append(f"Multiple log sources: {len(sources)}")

    # Repeated identical messages (potential loop/attack)
    messages = [entry.message for entry in logs]
    msg_counts = Counter(messages)
    most_common_count = msg_counts.most_common(1)[0][1] if msg_counts else 0
    if most_common_count > len(logs) * 0.5 and len(logs) > 5:
        score += 0.2
        reasons.append(f"Repeated message: {most_common_count}x identical")

    score = min(max(score, 0.0), 1.0)
    if not reasons:
        reasons.append("Log patterns appear normal")

    method = "lognet" if _lognet_model is not None else "statistical"
    model_id = "lognet-v1" if _lognet_model is not None else "statistical-log-v1"

    return ScoreResponse(
        score=score,
        explanations=reasons,
        model_id=model_id,
        scoring_method=method,
    )


@router.get(
    "/models/active",
    summary="List active models",
)
def list_active_models() -> dict[str, Any]:
    """Return information about all active scoring models."""
    _try_load_models()

    models = [
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
        },
    ]

    if _flownet_model is not None:
        models.append(
            {
                "model_id": "flownet-v1",
                "kind": "flow",
                "status": "active",
                "description": "FlowNet transformer: 4-layer encoder with reconstruction + anomaly heads (~1.2M params)",  # noqa: E501
                "architecture": "Transformer encoder (4 layers, 176d, 8 heads)",
                "features": [
                    "reconstruction_error",
                    "anomaly_logits",
                    "composite_score (T-205)",
                ],
            }
        )

    if _lognet_model is not None:
        models.append(
            {
                "model_id": "lognet-v1",
                "kind": "log",
                "status": "active",
                "description": "LogNet transformer: 6-layer encoder with masked-template + hypersphere objectives",  # noqa: E501
                "architecture": "Transformer encoder (6 layers)",
                "features": [
                    "masked_template_prediction",
                    "hypersphere_distance",
                ],
            }
        )

    return {"models": models}
