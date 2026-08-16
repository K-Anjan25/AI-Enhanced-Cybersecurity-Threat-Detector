"""Model training library (reusable by the CLI and the in-service retrain).

Contains the same training logic as the historical ``train.py`` CLI, factored
into callable functions so the ml-service can expose a ``POST /retrain``
endpoint (FR-STREAM-05 runtime automation). Each run emits fresh ``.pkl``
artifacts plus a versioned ``manifest.json`` consumed by ``GET /models``.

Serving correctness: the serving modules cache models in memory at first use.
After a retrain the caller MUST call each ``*.reload()`` so the next predictions
use the new artifacts instead of stale in-memory models.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_CICIDS_PATH = "../datasets/CICIDS2017/*.csv"
DEFAULT_MODEL_DIR = "model"

NETWORK_FEATURES = [
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

LOG_SAMPLES = [
    ("INFO", "User login successful", 0),
    ("INFO", "File accessed normally", 0),
    ("INFO", "System started successfully", 0),
    ("INFO", "Scheduled backup completed", 0),
    ("INFO", "Configuration reloaded", 0),
    ("INFO", "Heartbeat received from node", 0),
    ("INFO", "Email queued for delivery", 0),
    ("INFO", "Metrics collected", 0),
    ("INFO", "Session established", 0),
    ("INFO", "Request completed in 42ms", 0),
    ("ERROR", "Multiple failed login attempts detected", 1),
    ("WARNING", "Unauthorized access attempt detected", 1),
    ("CRITICAL", "Database brute force attack detected", 1),
    ("ERROR", "SQL injection attempt blocked", 1),
    ("CRITICAL", "Kernel memory corruption exploit", 1),
    ("WARNING", "Privilege escalation detected", 1),
    ("CRITICAL", "Ransomware encryption activity on filesystem", 1),
    ("ERROR", "Malware signature matched: trojan.win32", 1),
    ("WARNING", "Port scan activity from external host", 1),
    ("CRITICAL", "Data exfiltration via DNS tunneling suspected", 1),
    ("ERROR", "Buffer overflow attempt on service port", 1),
    ("WARNING", "Phishing link detected in inbound email", 1),
]

EMAIL_SAMPLES = [
    ("Your monthly statement is ready", "Dear customer, your invoice for March is now available in your portal. Please review at your convenience.", 0),
    ("Re: Project status update", "Hi team, here is the updated status report for the security dashboard project. Let me know your feedback.", 0),
    ("Meeting invitation", "You are invited to a meeting tomorrow at 10am in room B4. Please confirm attendance.", 0),
    ("Build notification", "The nightly build completed successfully with zero failing tests. Artifacts are published.", 0),
    ("Newsletter", "Here is this week's security briefing covering the latest advisories and patch guidance.", 0),
    ("Receipt", "Thank you for your purchase. Your order has shipped and will arrive within 3 business days.", 0),
    ("Password reset confirmation", "Your password was successfully changed. If this was not you, contact support.", 0),
    ("Onboarding doc", "Welcome aboard! Please review the employee handbook and complete your onboarding tasks.", 0),
    ("URGENT: Account verification required", "We detected unusual activity on your account. Click here to verify your credentials immediately or your account will be suspended within 24 hours.", 1),
    ("Your account has been locked", "Dear customer, your account has been locked. Visit http://secure-verify-now.com/login to unlock with your password and credit card details.", 1),
    ("Unusual sign-in detected", "Click the link below to confirm it was you. Do not reply to this email. Update your SSN and bank details now.", 1),
    ("Wire transfer confirmation", "Your transfer of $9,500 is pending. Click here with your banking password to confirm. Hurry, limited time!", 1),
    ("Prize claim", "Congratulations! You won $1,000,000. Send your bank account and SSN to claim your prize before midnight.", 1),
    ("Invoice attached", "Please download the attached invoice at 209.85.233.81/pay to settle your overdue balance immediately.", 1),
    ("Security alert - respond now", "Your mailbox exceeded its quota. Click immediately to re-verify with your password to avoid deletion.", 1),
    ("CFO request: urgent transfer", "I am in a meeting. Wire $25,000 to this account today and send the receipt. Do not discuss with anyone.", 1),
]


def _now_version() -> str:
    """Version string = UTC timestamp, e.g. ``20260812T031500Z``."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def train_log_model(model_dir: str) -> dict:
    """Fit the TF-IDF + LogisticRegression log classifier. Returns a manifest dict."""
    samples = LOG_SAMPLES * 400
    messages = [f"[{level}] {msg}" for level, msg, _label in samples]
    labels = [label for _l, _m, label in samples]

    X_train, X_test, y_train, y_test = train_test_split(
        messages, labels, test_size=0.2, random_state=42
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("classifier", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(X_train, y_train)
    accuracy = float(pipeline.score(X_test, y_test))

    joblib.dump(pipeline, os.path.join(model_dir, "log_model.pkl"))
    return {"model": "log_model", "status": "trained", "accuracy": round(accuracy, 4)}


def train_email_model(model_dir: str) -> dict:
    """Fit the TF-IDF + LogisticRegression email phishing classifier."""
    samples = EMAIL_SAMPLES * 300
    texts = [f"[SUBJECT] {subj} [BODY] {body}" for subj, body, _label in samples]
    labels = [label for _s, _b, label in samples]

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("classifier", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(X_train, y_train)
    accuracy = float(pipeline.score(X_test, y_test))

    joblib.dump(pipeline, os.path.join(model_dir, "email_model.pkl"))
    return {"model": "email_model", "status": "trained", "accuracy": round(accuracy, 4)}


def train_network_model(model_dir: str, cicids_path: str) -> dict:
    """Fit the IsolationForest network model from CICIDS CSVs.

    Raises FileNotFoundError/KeyError when the dataset is missing or lacks the
    expected columns, so the CLI can fail loudly while the in-service retrain
    can skip this model gracefully.
    """
    cic_files = glob.glob(cicids_path)
    if not cic_files:
        raise FileNotFoundError(f"No CSV datasets found at {cicids_path}")

    dfs = []
    for file in cic_files:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()
        dfs.append(df)
    cic_data = pd.concat(dfs, ignore_index=True)

    missing = [c for c in NETWORK_FEATURES if c not in cic_data.columns]
    if missing:
        raise KeyError(f"Missing expected columns in dataset: {missing}")

    X_raw = cic_data[NETWORK_FEATURES].copy()
    X_raw.replace([np.inf, -np.inf], np.nan, inplace=True)
    X_clean = X_raw.dropna()

    if len(X_clean) > 200000:
        X = X_clean.sample(n=200000, random_state=42)
    else:
        X = X_clean

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("isolation", IsolationForest(
            contamination=0.05, n_estimators=100, random_state=42, n_jobs=-1
        )),
    ])
    pipeline.fit(X)
    joblib.dump(pipeline, os.path.join(model_dir, "network_model.pkl"))
    return {"model": "network_model", "status": "trained", "samples": int(len(X))}


def run_training(
    model_dir: str = DEFAULT_MODEL_DIR,
    cicids_path: str = DEFAULT_CICIDS_PATH,
    require_network: bool = True,
) -> dict:
    """Train every model into ``model_dir`` and write a versioned manifest.

    Returns the manifest dict (also persisted to ``model/manifest.json``).
    ``require_network=False`` skips the network model (with a ``skipped`` status)
    when the CICIDS dataset is absent — used by the in-cluster retrain CronJob.
    """
    os.makedirs(model_dir, exist_ok=True)

    results: list[dict] = []
    results.append(train_log_model(model_dir))
    results.append(train_email_model(model_dir))
    try:
        results.append(train_network_model(model_dir, cicids_path))
    except (FileNotFoundError, KeyError) as exc:
        if require_network:
            raise
        results.append({"model": "network_model", "status": "skipped", "reason": str(exc)})

    manifest = {
        "version": _now_version(),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "models": results,
    }

    manifest_path = os.path.join(model_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    return manifest


def load_manifest(model_dir: str = DEFAULT_MODEL_DIR) -> Optional[dict]:
    """Read the persisted training manifest (None if a run never happened)."""
    path = os.path.join(model_dir, "manifest.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def load_manifest_benchmark(model_dir: str = DEFAULT_MODEL_DIR) -> Optional[dict]:
    """Read the persisted benchmark report (None if a run never happened)."""
    path = os.path.join(model_dir, "benchmark.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None