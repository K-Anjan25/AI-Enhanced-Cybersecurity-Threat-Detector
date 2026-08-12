import os

import joblib

from app.feature_extractor import score_to_severity

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model", "log_model.pkl")
MODEL_PATH = os.path.abspath(MODEL_PATH)

ATTACK_THRESHOLD = 0.6

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


def _to_dict(data) -> dict:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def predict_log(log) -> dict:
    log = _to_dict(log)
    message = str(log.get("message") or log.get("msg") or "")
    level = str(log.get("level") or "INFO").upper()
    formatted_input = f"[{level}] {message}"

    model, error = _load_model()
    indicators = []

    if model is None:
        # Heuristic fallback keyword scorer.
        score = 0.0
        lowered = formatted_input.lower()
        for kw, weight in [("failed login", 0.25), ("unauthorized", 0.3), ("brute", 0.35),
                           ("sql injection", 0.4), ("exploit", 0.4), ("privilege escalation", 0.4),
                           ("malware", 0.45), ("ransomware", 0.5), ("buffer overflow", 0.5),
                           ("ddos", 0.35), ("backdoor", 0.5), ("breach", 0.45)]:
            if kw in lowered:
                score += weight
                indicators.append(kw)
        if level in ("ERROR", "CRITICAL"):
            score += 0.15
            indicators.append(f"log level {level}")
        score = min(score, 1.0)
        is_attack = score >= ATTACK_THRESHOLD
        return {
            "anomaly_score": round(score, 4),
            "is_anomaly": bool(is_attack),
            "severity": score_to_severity(score),
            "confidence": 0.65,
            "indicators": list(dict.fromkeys(indicators)),
            "model": "log_heuristic",
        }

    probability = float(model.predict_proba([formatted_input])[0][1])
    is_attack = probability >= ATTACK_THRESHOLD
    if is_attack:
        indicators.append("matches learned attack signature")
        if level in ("ERROR", "CRITICAL"):
            indicators.append(f"log level {level}")

    return {
        "anomaly_score": round(probability, 4),
        "is_anomaly": bool(is_attack),
        "severity": score_to_severity(probability),
        "confidence": round(float(min(0.99, abs(probability - 0.5) * 2 + 0.5)), 3),
        "indicators": indicators,
        "model": "log_classifier",
        "raw_probability": round(probability, 4),
    }
