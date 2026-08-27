"""Model explainability (dependency-free).

Explains WHY a prediction was made, without the SHAP/Mamba heavy stack:

- **log / email** (TF-IDF + LogisticRegression): top contributing n-grams, from
  the pipeline's coefficients when a model is loaded, falling back to the
  heuristic keyword/pattern weights.
- **network** (IsolationForest): per-feature deviation from the training
  centroid (via the scaler in the pipeline, else the rule-based heuristics).
- **DNS** (rule engine): the fired rules are themselves the explanation.

Every function returns a stable shape so the API and the UI can render
``contributions`` generically.
"""

from __future__ import annotations

import re

import numpy as np


def _contrib_log_with_model(text: str, pipeline) -> list[dict]:
    """Top n-grams by coefficient magnitude from the trained classifier."""
    try:
        vec = pipeline.named_steps["tfidf"]
        clf = pipeline.named_steps["classifier"]
        coef = np.asarray(clf.coef_[0])
        vocab = vec.get_feature_names_out()
        matrix = vec.transform([text])
        term_idx = matrix.nonzero()[1]
        contribs = {}
        for idx in term_idx:
            word = vocab[idx]
            # Raw coefficient * tf weight approximates the term's influence.
            weight = float(matrix[0, idx]) * float(coef[idx])
            if abs(weight) < 1e-6:
                continue
            contribs[word] = (weight, weight > 0)
        ranked = sorted(contribs.items(), key=lambda kv: abs(kv[1][0]), reverse=True)[:8]
        return [
            {
                "term": word,
                "score": round(float(value), 4),
                # direction: positive coef => pushes toward the attack class,
                # negative coef => pushes toward benign.
                "direction": "attack" if positive else "benign",
            }
            for word, (value, positive) in ranked
        ]
    except Exception:  # pragma: no cover - defensive, model internals vary
        return []


def _contrib_log_heuristic(text: str) -> list[dict]:
    from app.feature_extractor import THREAT_KEYWORDS

    lowered = text.lower()
    return [
        {"term": kw, "score": score, "direction": "attack", "source": "keyword"}
        for kw, score in sorted(
            THREAT_KEYWORDS.items(), key=lambda item: item[1], reverse=True
        )
        if kw in lowered
    ][:8]


def explain_log(log) -> dict:
    from app.log_model import _load_model

    log = log if isinstance(log, dict) else log.model_dump()
    text = f"[{str(log.get('level') or 'INFO').upper()}] {log.get('message') or ''}"

    model, error = _load_model()
    contributions = _contrib_log_with_model(text, model) if model is not None else _contrib_log_heuristic(text)

    # Mirror the heuristic keyword breakdown even when a model exists, so
    # analysts always see human-readable rationale.
    if model is not None:
        keywords = _contrib_log_heuristic(text)
        if not contributions:
            contributions = keywords
        seen = {c["term"] for c in contributions}
        for kw in keywords:
            if kw["term"] not in seen:
                contributions.append(kw)

    return {
        "contributions": contributions[:8],
        "summary": _summarize(contributions),
        "method": "coefficients + keyword evidence",
        "model_error": error,
    }


def _contrib_email_with_model(text: str, pipeline) -> list[dict]:
    return _contrib_log_with_model(text, pipeline)


def explain_email(email) -> dict:
    from app.email_model import PHISHY_PATTERNS, _load_model

    email = email if isinstance(email, dict) else email.model_dump()
    subject = str(email.get("subject") or "")
    body = str(email.get("body") or "")
    text = f"[SUBJECT] {subject} [BODY] {body}".lower()

    model, error = _load_model()
    contributions = _contrib_email_with_model(text, model) if model is not None else []

    # Heuristic pattern evidence always shown (explainable + blends with model).
    for pattern, weight, label in PHISHY_PATTERNS:
        if re.search(pattern, text):
            contributions.append({"term": label, "score": round(weight, 3), "direction": "attack", "source": "pattern"})

    if not contributions:
        contributions.append({"term": "no suspicious signals", "score": 0.0, "direction": "benign", "source": "none"})

    return {
        "contributions": contributions[:8],
        "summary": _summarize(contributions),
        "method": "coefficients + phishing patterns",
        "model_error": error,
    }


def _feature_label(col: str) -> str:
    labels = {
        "Destination Port": "destination port",
        "Flow Duration": "flow duration",
        "Total Fwd Packets": "total forward packets",
        "Total Backward Packets": "total backward packets",
        "Total Length of Fwd Packets": "forward bytes",
        "Total Length of Bwd Packets": "backward bytes",
        "Fwd Packet Length Mean": "forward packet mean length",
        "Bwd Packet Length Mean": "backward packet mean length",
        "Flow Bytes/s": "bytes per second",
        "Flow Packets/s": "packets per second",
        "Average Packet Size": "average packet size",
        "Init_Win_bytes_forward": "init window bytes",
    }
    return labels.get(col, col.lower().replace("_", " "))


def explain_network(data) -> dict:
    from app.network_model import TRAIN_COLUMNS, _load_model

    data = data if isinstance(data, dict) else data.model_dump()
    model, error = _load_model()
    contributions = []

    if model is not None:
        try:
            scaler = model.named_steps["scaler"]
            mean = np.asarray(scaler.mean_)
            std = np.asarray(scaler.scale_)

            row = {col: 0.0 for col in TRAIN_COLUMNS}
            row["Destination Port"] = float(data.get("dst_port", 0) or 0)
            row["Flow Duration"] = float(data.get("duration", 0) or 0)
            row["Total Fwd Packets"] = float(data.get("total_fwd_packets", 0) or 0)
            row["Total Backward Packets"] = float(data.get("total_bwd_packets", 0) or 0)
            row["Total Length of Fwd Packets"] = float(data.get("bytes", 0) or 0)
            row["Total Length of Bwd Packets"] = float(data.get("total_length_bwd_packets", 0) or 0)
            row["Fwd Packet Length Mean"] = float(data.get("fwd_packet_length_mean", 0) or 0)
            row["Bwd Packet Length Mean"] = float(data.get("bwd_packet_length_mean", 0) or 0)
            duration = float(data.get("duration", 0) or 0)
            row["Flow Bytes/s"] = float(row["Total Length of Fwd Packets"]) / duration if duration > 0 else 0.0
            row["Flow Packets/s"] = float(data.get("flow_packets_s", 0) or 0)
            row["Average Packet Size"] = float(data.get("avg_packet_size", 0) or 0)
            row["Init_Win_bytes_forward"] = float(data.get("init_win_bytes_forward", 0) or 0)

            deviations = []
            for i, col in enumerate(TRAIN_COLUMNS):
                if std[i] == 0:
                    continue
                z = abs((row[col] - mean[i]) / std[i])
                deviations.append((z, col))
            for z, col in sorted(deviations, reverse=True)[:6]:
                contributions.append({
                    "term": _feature_label(col),
                    "score": round(float(z), 3),
                    "direction": "attack" if z >= 3.0 else "attention",
                    "source": "deviation from training centroid",
                })
        except Exception:  # pragma: no cover - defensive
            contributions = []

    if model is None:
        # Rule-based fallback: surface the heuristic indicators that
        # predict_network itself would fire, so the explanation is never empty.
        from app.network_model import predict_network

        result = predict_network(data)
        for ind in result.get("indicators", []):
            contributions.append({
                "term": ind,
                "score": round(float(result.get("anomaly_score", 0.0)), 3),
                "direction": "attack" if result.get("is_anomaly") else "attention",
                "source": "rules",
            })
        if not contributions:
            contributions.append({
                "term": "no rule-based signals fired",
                "score": 0.0,
                "direction": "benign",
                "source": "rules",
            })

    return {
        "contributions": contributions[:6],
        "summary": _summarize(contributions),
        "method": "isolation-forest centroid deviation" if model is not None else "rules",
        "model_error": error,
    }


def explain_dns(dns) -> dict:
    from app.dns_model import predict_domain

    result = predict_domain(dns)
    return {
        "contributions": [
            {"term": ind, "score": round(result["anomaly_score"], 3), "direction": "attack", "source": "rule"}
            for ind in result.get("indicators", [])
        ],
        "summary": _summarize([{"term": i} for i in result.get("indicators", [])]),
        "method": "rule engine",
        "model_error": None,
    }


def _summarize(contributions: list[dict]) -> str:
    if not contributions:
        return "No strong signals detected for this input."
    attack = [c["term"] for c in contributions if c.get("direction") == "attack"]
    if attack:
        return "Driven by: " + ", ".join(attack[:4]) + "."
    return "No attack-driving signals; the prediction leans benign."