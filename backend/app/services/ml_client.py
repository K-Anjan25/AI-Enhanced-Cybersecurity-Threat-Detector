from datetime import datetime, timezone

import requests
from app.core.config import settings


def _post_with_retry(url: str, json, timeout: float = 10.0, max_retries: int = 2) -> dict:
    """POST with retries and exponential backoff when the ML service is down."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=json, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - network errors are expected
            last_error = exc
            if attempt < max_retries:
                import time
                time.sleep(0.3 * (2 ** attempt))
    raise requests.ConnectionError(f"ML service unreachable after {max_retries + 1} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Heuristic fallback classification (runs when the ML service is unreachable so
# a dead svc never turns into a failed scan).
# ---------------------------------------------------------------------------

_SUSPICIOUS_LOG_INDICATORS = [
    "failed password", "failed login", "login failed", "brute", "sql injection",
    "malware", "ransomware", "root", "shell", "unauthorized", "permission denied",
    "invalid user", "connection refused", "port scan", "tunnel", "exfil", "ddos",
]


def fallback_predict_log(data: dict) -> dict:
    """Heuristic log classifier: keyword + length heuristics in 0..1 score space."""
    message = (data.get("message") or "").lower()
    score = 0.0
    indicators = []
    for keyword in _SUSPICIOUS_LOG_INDICATORS:
        if keyword in message:
            indicators.append(keyword)
            score += 0.5
    if len(message) > 500:
        score += 0.15
    score = min(score, 1.0)
    return {
        "anomaly_score": round(score, 4),
        "is_anomaly": score >= 0.4,
        "severity": "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW"),
        "fallback": True,
        "indicators": indicators,
    }


def fallback_predict_network(data: dict) -> dict:
    """Heuristic network classifier based on volume/duration/packet heuristics."""
    try:
        bytes_ = float(data.get("bytes") or 0)
        duration = float(data.get("duration") or 0)
        packets = float(data.get("packets") or data.get("total_fwd_packets", 0) or 0)
    except (TypeError, ValueError):
        bytes_ = duration = packets = 0.0

    score = 0.0
    if duration > 0:
        if packets / duration > 200:
            score += 0.55
        if bytes_ / duration > 5_000_000:
            score += 0.5
    if bytes_ > 10_000_000:
        score += 0.3
    score = min(score, 1.0)
    return {
        "anomaly_score": round(score, 4),
        "is_anomaly": score >= 0.4,
        "severity": "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW"),
        "fallback": True,
    }


# ---------------------------------------------------------------------------
# Public prediction helpers
# ---------------------------------------------------------------------------

def predict_network(data: dict):
    try:
        result = _post_with_retry(f"{settings.ML_SERVICE_URL}/predict/network", data)
    except requests.ConnectionError:
        return fallback_predict_network(data)
    return result


def predict_log(data: dict):
    current_time = datetime.now(timezone.utc).isoformat()

    payload = {
        "timestamp": data.get("timestamp") or current_time,
        "level": data.get("level") or "INFO",
        "message": data.get("message") or data.get("content") or str(data.get("log_line", "")),
        "source": data.get("source") or "system"
    }

    try:
        result = _post_with_retry(f"{settings.ML_SERVICE_URL}/predict/log", payload)
    except requests.ConnectionError:
        return fallback_predict_log(payload)
    return result


def predict_log_batch(items: list[dict]):
    # ensure each entry is formatted correctly
    payloads = []
    for d in items:
        current_time = datetime.now(timezone.utc).isoformat()
        payloads.append({
            "timestamp": d.get("timestamp") or current_time,
            "level": d.get("level") or "INFO",
            "message": d.get("message") or d.get("content") or str(d.get("log_line", "")),
            "source": d.get("source") or "system"
        })

    try:
        return _post_with_retry(
            f"{settings.ML_SERVICE_URL}/predict/log/batch",
            payloads,
            timeout=30,
        )
    except requests.ConnectionError:
        return [fallback_predict_log(p) for p in payloads]
