"""Model benchmark harness.

Evaluates the *deployed* artifacts (``model/*.pkl``) against deterministic
holdout sets so the numbers reflect what is actually being served — not a
re-fit inside a test.

- **log / email**: TF-IDF + LogisticRegression pipelines evaluated on a 20%
  holdout split of the same sample corpora used for training. Reports accuracy,
  precision, recall, F1.
- **network**: IsolationForest has no ground-truth labels, so the report covers
  training sample size, expected contamination, and the outlier rate the model
  actually assigns on a fresh subsample (CICIDS). When the dataset is absent the
  section is marked ``skipped`` rather than failing.

The harness is callable as a library (``run_benchmark()``), exposed as a FastAPI
endpoint, and runnable as a CLI (``python -m app.benchmark``). It writes a
versioned report to ``model/benchmark.json``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

from app.training import (
    DEFAULT_CICIDS_PATH,
    DEFAULT_MODEL_DIR,
    EMAIL_SAMPLES,
    LOG_SAMPLES,
    NETWORK_FEATURES,
)

_log_text = lambda samples: [f"[{level}] {msg}" for level, msg, _lbl in samples]  # noqa: E731
_email_text = lambda samples: [f"[SUBJECT] {subj} [BODY] {body}" for subj, body, _lbl in samples]  # noqa: E731


def _split(samples, text_fn):
    texts = text_fn(samples * 300)
    labels = [lbl for _x, _y, lbl in samples] * 300
    return train_test_split(texts, labels, test_size=0.2, random_state=42)


def _classify_metrics(model, X_test, y_test):
    y_pred = model.predict(X_test)
    return {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
    }


def benchmark_log(model_dir: str) -> dict:
    path = os.path.join(model_dir, "log_model.pkl")
    if not os.path.exists(path):
        return {"model": "log_model", "status": "skipped", "reason": "artifact missing"}
    model = joblib.load(path)
    X_train, X_test, y_train, y_test = _split(LOG_SAMPLES, _log_text)
    return {
        "model": "log_model",
        "status": "ok",
        "model_type": "TF-IDF + LogisticRegression",
        "test_samples": len(y_test),
        "metrics": _classify_metrics(model, X_test, y_test),
        "artifact": os.path.basename(path),
    }


def benchmark_email(model_dir: str) -> dict:
    path = os.path.join(model_dir, "email_model.pkl")
    if not os.path.exists(path):
        return {"model": "email_model", "status": "skipped", "reason": "artifact missing"}
    model = joblib.load(path)
    X_train, X_test, y_train, y_test = _split(EMAIL_SAMPLES, _email_text)
    return {
        "model": "email_model",
        "status": "ok",
        "model_type": "TF-IDF + LogisticRegression",
        "test_samples": len(y_test),
        "metrics": _classify_metrics(model, X_test, y_test),
        "artifact": os.path.basename(path),
    }


def benchmark_network(model_dir: str, cicids_path: str) -> dict:
    path = os.path.join(model_dir, "network_model.pkl")
    if not os.path.exists(path):
        return {"model": "network_model", "status": "skipped", "reason": "artifact missing"}

    import glob

    cic_files = glob.glob(cicids_path)
    if not cic_files:
        return {
            "model": "network_model",
            "status": "skipped",
            "reason": f"no CICIDS dataset at {cicids_path}",
        }

    dfs = []
    for file in cic_files:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()
        dfs.append(df)
    cic_data = pd.concat(dfs, ignore_index=True)

    missing = [c for c in NETWORK_FEATURES if c not in cic_data.columns]
    if missing:
        return {"model": "network_model", "status": "skipped", "reason": f"missing columns {missing}"}

    X_raw = cic_data[NETWORK_FEATURES].copy()
    X_raw.replace([np.inf, -np.inf], np.nan, inplace=True)
    X_clean = X_raw.dropna().sample(n=min(50_000, len(X_raw.dropna())), random_state=7)

    model = joblib.load(path)
    preds = model.predict(X_clean)
    scores = model.decision_function(X_clean)
    outlier_rate = float((preds == -1).mean())

    return {
        "model": "network_model",
        "status": "ok",
        "model_type": "IsolationForest (anomaly detection)",
        "benchmarked_samples": int(len(X_clean)),
        "metrics": {
            "observed_outlier_rate": round(outlier_rate, 4),
            "expected_contamination": round(float(model.named_steps["isolation"].contamination), 4),
            "mean_decision_score": round(float(scores.mean()), 4),
            "std_decision_score": round(float(scores.std()), 4),
        },
        "artifact": os.path.basename(path),
    }


def run_benchmark(
    model_dir: str = DEFAULT_MODEL_DIR,
    cicids_path: str = DEFAULT_CICIDS_PATH,
    persist: bool = True,
) -> dict:
    """Run every benchmark and (optionally) persist a versioned report."""
    report = {
        "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "models": [
            benchmark_log(model_dir),
            benchmark_email(model_dir),
            benchmark_network(model_dir, cicids_path),
        ],
    }

    if persist:
        os.makedirs(model_dir, exist_ok=True)
        report_path = os.path.join(model_dir, "benchmark.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    return report


if __name__ == "__main__":
    import sys

    report = run_benchmark(
        model_dir=sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_DIR,
        cicids_path=sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CICIDS_PATH,
    )
    print(json.dumps(report, indent=2))
