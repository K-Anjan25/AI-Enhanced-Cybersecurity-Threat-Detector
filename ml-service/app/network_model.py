import os

import joblib
import numpy as np
import pandas as pd

from app.feature_extractor import score_to_severity

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model", "network_model.pkl")
MODEL_PATH = os.path.abspath(MODEL_PATH)

# Feature columns must match what was used during training (see train.py).
TRAIN_COLUMNS = [
    "Destination Port",
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",
    "Fwd Packet Length Mean",
    "Bwd Packet Length Mean",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Average Packet Size",
    "Init_Win_bytes_forward",
]

_model = None
_model_error = None


def _load_model():
    global _model, _model_error
    if _model is not None or _model_error is not None:
        return _model, _model_error
    if not os.path.exists(MODEL_PATH):
        _model_error = f"model not found at {MODEL_PATH}"
        return None, _model_error
    try:
        _model = joblib.load(MODEL_PATH)
    except Exception as exc:  # pragma: no cover - defensive
        _model_error = f"failed to load model: {exc}"
        _model = None
    return _model, _model_error


def model_status() -> dict:
    model, error = _load_model()
    return {"loaded": model is not None, "error": error}


def reload() -> dict:
    """Drop cached artifacts so the next prediction loads the fresh model."""
    global _model, _model_error
    _model = None
    _model_error = None
    model, error = _load_model()
    return {"loaded": model is not None, "error": error}


def _to_dict(data) -> dict:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def predict_network(data) -> dict:
    """
    Predict anomaly for network traffic.
    IsolationForest: score >= 0 = normal, score < 0 = anomalous.
    Returns a dict with anomaly_score (0..1), is_anomaly, severity, confidence, indicators.
    """
    data = _to_dict(data)
    model, error = _load_model()
    indicators = []

    if model is None:
        # Deterministic fallback: heuristic based on suspicious ports and traffic volume.
        dst_port = int(data.get("dst_port", 0) or 0)
        duration = float(data.get("duration", 0) or 0)
        volume = float(data.get("bytes", 0) or 0)
        suspicious_ports = {21, 22, 23, 25, 445, 1433, 3306, 3389, 4444, 5555, 6667, 8080}
        score = 0.0
        if dst_port in suspicious_ports:
            score += 0.3
            indicators.append(f"suspicious destination port {dst_port}")
        if duration > 0 and volume / duration > 1_000_000:
            score += 0.4
            indicators.append("abnormally high byte throughput")
        if volume > 1_000_000_000:
            score += 0.3
            indicators.append("excessive data volume")
        if not indicators:
            score = 0.1
        return {
            "anomaly_score": round(min(score, 1.0), 4),
            "is_anomaly": score >= 0.6,
            "severity": score_to_severity(score),
            "confidence": 0.6,
            "indicators": indicators,
            "model": "network_heuristic",
        }

    row = {col: 0 for col in TRAIN_COLUMNS}
    row["Destination Port"] = data.get("dst_port", 0)
    row["Flow Duration"] = data.get("duration", 0)
    row["Total Fwd Packets"] = data.get("total_fwd_packets", 0)
    row["Total Backward Packets"] = data.get("total_bwd_packets", 0)
    row["Total Length of Fwd Packets"] = data.get("bytes", 0)
    row["Total Length of Bwd Packets"] = data.get("total_length_bwd_packets", 0)
    row["Fwd Packet Length Mean"] = data.get("fwd_packet_length_mean", 0)
    row["Bwd Packet Length Mean"] = data.get("bwd_packet_length_mean", 0)
    duration = float(data.get("duration", 0) or 0)
    row["Flow Bytes/s"] = float(data.get("bytes", 0) or 0) / duration if duration > 0 else 0.0
    row["Flow Packets/s"] = data.get("flow_packets_s", 0)
    row["Average Packet Size"] = data.get("avg_packet_size", 0)
    row["Init_Win_bytes_forward"] = data.get("init_win_bytes_forward", 0)

    features = pd.DataFrame([row], columns=TRAIN_COLUMNS).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    raw = float(model.decision_function(features)[0])
    prediction = int(model.predict(features)[0])
    is_anomaly = prediction == -1

    # Normalize IsolationForest score (-0.7..0.5 typical) into a 0..1 anomaly score.
    score = float(np.clip((0.5 - raw) / 1.2, 0.0, 1.0))
    if is_anomaly and score < 0.6:
        score = 0.6

    dst_port = int(data.get("dst_port", 0) or 0)
    if is_anomaly:
        indicators.append("outlier in feature space (isolation forest)")
        if dst_port in {22, 23, 445, 3389, 1433, 3306, 8080}:
            indicators.append(f"sensitive port {dst_port} targeted")

    return {
        "anomaly_score": round(score, 4),
        "is_anomaly": bool(is_anomaly),
        "severity": score_to_severity(score),
        "confidence": round(float(np.clip(abs(0.5 - raw) + 0.5, 0.5, 0.99)), 3),
        "indicators": indicators,
        "model": "isolation_forest",
        "raw_score": round(raw, 4),
    }
