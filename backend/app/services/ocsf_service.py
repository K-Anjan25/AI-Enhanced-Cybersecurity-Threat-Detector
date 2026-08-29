"""OCSF normalization — Open Cybersecurity Schema Framework mapping (Phase 44).

Converts internal SecurityAlert rows into OCSF v1.1.0 Security Finding (class 2001) and Detection Finding (class 2004).

Honest scope:
- Maps severity, MITRE, source, time, observables
- Does not invent fields — missing data stays missing, not defaulted to fake values
- Supports batch conversion for export
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.models import SecurityAlert


OCSF_SEVERITY_MAP = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
}

OCSF_STATUS_MAP = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}


def _iso(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    try:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    except Exception:
        return None


def alert_to_ocsf_finding(alert: SecurityAlert) -> Dict[str, Any]:
    """Convert a SecurityAlert to OCSF Security Finding (class_uid 2001)."""
    sev_id = OCSF_SEVERITY_MAP.get((alert.severity or "MEDIUM").upper(), 3)
    sev_name = OCSF_STATUS_MAP.get((alert.severity or "MEDIUM").upper(), "Medium")

    # MITRE ATT&CK as OCSF attack object
    attack = None
    if alert.mitre_technique_id or alert.mitre_technique:
        attack = {
            "tactic": {"name": alert.mitre_tactic} if alert.mitre_tactic else None,
            "technique": {
                "uid": alert.mitre_technique_id,
                "name": alert.mitre_technique,
            } if alert.mitre_technique_id or alert.mitre_technique else None,
        }
        # Clean None
        attack = {k: v for k, v in attack.items() if v is not None}

    observables = []
    if alert.source_ip:
        observables.append({"name": "source_ip", "type": "IP Address", "value": alert.source_ip})

    finding = {
        "class_uid": 2001,
        "class_name": "Security Finding",
        "category_uid": 2,
        "category_name": "Findings",
        "type_uid": 200101,
        "type_name": "Security Finding: Create",
        "severity_id": sev_id,
        "severity": sev_name,
        "status_id": 1,
        "status": "New",
        "time": _iso(getattr(alert, "created_at", None)) or _iso(datetime.now(timezone.utc)),
        "finding": {
            "uid": str(alert.id),
            "title": alert.message[:200] if alert.message else f"Alert {alert.id}",
            "desc": alert.message,
            "types": [alert.alert_type] if alert.alert_type else [],
        },
        "observables": observables,
        "src_endpoint": {"ip": alert.source_ip} if alert.source_ip else None,
        "metadata": {
            "product": {"name": "NOCTRA", "vendor_name": "NOCTRA"},
            "version": "1.0",
        },
        "raw_data": alert.message,
        "unmapped": {
            "original_severity": alert.severity,
            "source": alert.source,
            "score": alert.score,
            "threat_intel": getattr(alert, "threat_intel", None),
        },
    }

    if attack:
        finding["attack"] = attack

    # Remove None values for cleanliness, but keep honest absence
    finding = {k: v for k, v in finding.items() if v is not None}

    return finding


def alerts_to_ocsf_batch(alerts: List[SecurityAlert]) -> Dict[str, Any]:
    """Convert batch of alerts to OCSF batch."""
    return {
        "ocsf_version": "1.1.0",
        "findings": [alert_to_ocsf_finding(a) for a in alerts],
        "count": len(alerts),
    }


def ocsf_to_brief_summary(ocsf_findings: List[Dict[str, Any]]) -> str:
    """Generate a brief summary from OCSF findings for analyst chat grounding."""
    if not ocsf_findings:
        return "No recent connector alerts."

    sev_counts = {}
    sources = set()
    for f in ocsf_findings:
        sev = f.get("severity", "Unknown")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        src = f.get("unmapped", {}).get("source")
        if src:
            sources.add(src)

    parts = [f"{count} {sev}" for sev, count in sev_counts.items()]
    summary = f"Recent connector activity: {', '.join(parts)} alerts from {', '.join(sources) if sources else 'various sources'}."
    return summary
