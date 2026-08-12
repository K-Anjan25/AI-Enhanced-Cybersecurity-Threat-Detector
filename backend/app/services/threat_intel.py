"""Threat-intelligence enrichment for incoming alerts.

Cross-references observed source IPs against the ``ip_reputation`` store
(populated via the IP Reputation endpoints) and attaches reputation context
(threat_score, category, blocked status) to alerts. If no record exists yet,
the IP is auto-registered so analysts get a stable reputation baseline.

The enrichment is **additive**: it never downgrades a detection — it only adds
``threat_intel`` context and can flag ``reputation_blocked`` for triage.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import IpReputation

# Threat-score bands used to describe reputation without exposing raw scores.
def band(threat_score: float) -> str:
    if threat_score >= 0.8:
        return "malicious"
    if threat_score >= 0.5:
        return "suspicious"
    if threat_score > 0.0:
        return "low"
    return "unknown"


def enrich_alert(db: Session, source_ip: Optional[str]) -> dict:
    """Return threat-intel context for ``source_ip`` (or an empty dict).

    Auto-registers unknown IPs with a neutral score so future events for the
    same address have a reputation record to query.
    """
    if not source_ip:
        return {}

    row = db.query(IpReputation).filter(IpReputation.ip_address == source_ip).first()
    if row is None:
        try:
            row = IpReputation(ip_address=source_ip, threat_score=0.0, is_blocked=False, category="observed")
            db.add(row)
            db.flush()
        except Exception:
            # Concurrent insert / constraint race — fall back to a re-read.
            db.rollback()
            row = db.query(IpReputation).filter(IpReputation.ip_address == source_ip).first()
            if row is None:
                return {}

    return {
        "ip_address": row.ip_address,
        "threat_score": row.threat_score,
        "category": row.category,
        "is_blocked": row.is_blocked,
        "reputation_band": band(row.threat_score),
    }
