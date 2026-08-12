import math
import re
import string

import numpy as np
import pandas as pd

# Keywords weighted by how strongly they correlate with malicious activity.
THREAT_KEYWORDS = {
    "error": 1,
    "failed": 1,
    "fail": 1,
    "unauthorized": 2,
    "denied": 1,
    "forbidden": 2,
    "blocked": 1,
    "invalid": 1,
    "exception": 1,
    "timeout": 1,
    "attack": 3,
    "brute": 3,
    "force": 2,
    "sql injection": 3,
    "exploit": 3,
    "malware": 3,
    "ransomware": 4,
    "trojan": 4,
    "intrusion": 3,
    "phishing": 3,
    "spoof": 2,
    "scan": 2,
    "port scan": 2,
    "privilege escalation": 4,
    "buffer overflow": 4,
    "xss": 3,
    "csrf": 2,
    "cve": 3,
    "ddos": 3,
    "botnet": 3,
    "credential": 2,
    "compromised": 3,
    "breach": 4,
    "exfiltrat": 4,
    "backdoor": 4,
    "rootkit": 4,
    "keylogger": 4,
    "cryptojack": 3,
    "suspicious": 2,
}


def extract_features(log: dict) -> pd.DataFrame:
    """Convert a raw log entry into a fixed-width numeric feature vector."""
    message = str(log.get("message") or log.get("msg") or "").lower()
    level = str(log.get("level") or "INFO").upper()
    source = str(log.get("source") or "system")

    words = re.findall(r"[a-z0-9]+", message)
    length = len(message)
    word_count = len(words)

    keyword_hits = {
        kw: (1 if kw in message else 0) for kw in [
            "error", "failed", "unauthorized", "attack", "brute", "exploit",
            "malware", "injection", "escalation", "scan", "phishing",
        ]
    }

    features = {
        "length": length,
        "word_count": word_count,
        "unique_ratio": len(set(words)) / word_count if word_count else 0.0,
        "uppercase_ratio": sum(1 for c in message if c.isupper()) / length if length else 0.0,
        "special_char_count": sum(1 for c in message if c in string.punctuation),
        "has_ip": int(bool(re.search(r"\d{1,3}(\.\d{1,3}){3}", message))),
        "has_url": int(bool(re.search(r"https?://|www\.", message))),
        "threat_keyword_score": sum(score for kw, score in THREAT_KEYWORDS.items() if kw in message),
        "level_rank": {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}.get(level, 1),
        "is_critical_level": int(level in ("ERROR", "CRITICAL")),
        "timestamp_present": int(bool(log.get("timestamp"))),
    }
    features.update(keyword_hits)

    return pd.DataFrame([features])


def score_to_severity(score: float) -> str:
    if score < 0.4:
        return "LOW"
    if score < 0.7:
        return "MEDIUM"
    if score < 0.9:
        return "HIGH"
    return "CRITICAL"


def confidence_from_score(score: float) -> float:
    """Map a 0..1 anomaly score to a confidence value, pushed away from 0.5."""
    return float(round(min(0.99, max(0.5, abs(score - 0.5) * 2 + 0.5)), 3))
