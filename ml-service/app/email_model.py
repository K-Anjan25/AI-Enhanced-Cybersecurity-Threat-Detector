import os
import re

import joblib

from app.feature_extractor import score_to_severity

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model", "email_model.pkl")
MODEL_PATH = os.path.abspath(MODEL_PATH)

ATTACK_THRESHOLD = 0.6

# Heuristic weights applied when the trained model is unavailable or in parallel
# with it to surface explainable indicators.
PHISHY_PATTERNS = [
    (r"verify.{0,30}(account|identity|credentials)", 0.3, "requests credential verification"),
    (r"(urgent|immediately|within 24 hours|account.*suspend)", 0.25, "urgency / deadline pressure"),
    (r"http[s]?://", 0.1, "contains a link"),
    (r"click.{0,20}(here|link)", 0.2, "click-bait wording"),
    (r"(password|ssn|credit card|bank|wire|paypal|bitcoin|crypto)", 0.3, "mentions sensitive data"),
    (r"\b(not reply|don'?t reply|unsubscribe|dear (valued )?customer)\b", 0.2, "generic greeting"),
    (r"\d{1,3}(\.\d{1,3}){3}", 0.2, "contains raw IP address"),
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


def predict_email(email) -> dict:
    email = _to_dict(email)
    sender = str(email.get("sender") or "")
    subject = str(email.get("subject") or "")
    body = str(email.get("body") or "")
    text = f"[SUBJECT] {subject} [BODY] {body}".lower()

    indicators = []
    heuristic_score = 0.0
    for pattern, weight, label in PHISHY_PATTERNS:
        if re.search(pattern, text):
            heuristic_score += weight
            indicators.append(label)

    if sender:
        local = sender.split("@")[0] if "@" in sender else sender
        digits_ratio = sum(c.isdigit() for c in local) / len(local) if local else 0
        if digits_ratio > 0.5:
            heuristic_score += 0.2
            indicators.append("sender local-part is mostly digits")
        if re.search(r"\d{1,3}(\.\d{1,3}){3}", sender):
            heuristic_score += 0.2
            indicators.append("sender address contains raw IP")

    model, error = _load_model()
    if model is not None:
        try:
            probability = float(model.predict_proba([text])[0][1])
            # Blend trained probability with heuristic evidence.
            blended = min(1.0, 0.7 * probability + 0.3 * min(heuristic_score, 1.0))
        except Exception:  # pragma: no cover - defensive
            blended = min(heuristic_score, 1.0)
    else:
        blended = min(heuristic_score, 1.0)

    is_attack = blended >= ATTACK_THRESHOLD
    if is_attack and "heuristic" not in [i for i in indicators]:
        indicators.append("matches learned phishing signature")
    indicators = list(dict.fromkeys(indicators))

    return {
        "anomaly_score": round(blended, 4),
        "is_anomaly": bool(is_attack),
        "severity": score_to_severity(blended),
        "confidence": round(float(min(0.99, abs(blended - 0.5) * 2 + 0.5)), 3),
        "indicators": indicators,
        "model": "email_model.pkl" if model is not None else "email_heuristic",
    }
