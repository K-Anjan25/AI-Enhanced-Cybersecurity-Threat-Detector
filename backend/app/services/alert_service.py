from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.ml_client import predict_network, predict_log
from app.services.kafka_producer import send_alert, send_normalized, send_raw_log, send_raw_flow
from app.services.mitre import map_alert
from app.services.threat_intel import enrich_alert
from app.services.entity_graph import index_alert
from app.services.soar import respond_to_alert
from app.core.database import SessionLocal
from app.models import SecurityAlert, ScannedAlert, DetectionRule
from app.utils.helpers import score_to_severity

# Session factory used by background scan tasks. Overridable in tests so the
# queued work writes to the test database (see tests/conftest.py).
session_factory = SessionLocal


def process_log(log: dict, produce_kafka: bool = True, db: Optional[Session] = None, org_id: Optional[int] = None) -> dict:
    """Run a single log/network record through the ML service and persist alerts.

    Network records are detected by the presence of traffic-specific fields.
    Everything else is treated as a system log entry.

    ``db`` optionally supplies the session to persist alerts in; when omitted a
    fresh session is created from :data:`session_factory`. ``org_id`` scopes the
    resulting alert to a tenant (multi-tenancy v3).

    Returns a normalized result dict (with a ``fallback`` flag when the ML
    service was unreachable and heuristics were used instead).
    """
    uses_own_session = db is None
    if db is None:
        db = session_factory()

    if "bytes" in log and "duration" in log:
        result = predict_network(log)
        source_ip = log.get("src_ip", "127.0.0.1")
        message = "Network traffic anomaly detected"
        alert_type = "network"
    else:
        result = predict_log(log)
        source_ip = log.get("source", "127.0.0.1")
        message = log.get("message", "System log analyzed")
        alert_type = "system_log"

    score = float(result.get("anomaly_score", 0.0))
    is_anomaly = bool(result.get("is_anomaly", False))
    severity = score_to_severity(score, model_type=alert_type)
    mitre = map_alert(alert_type, message, source_ip, log.get("dst_port"))
    intel = enrich_alert(db, source_ip)

    if produce_kafka:
        # Streaming event chain (FR-STREAM-01/02, FR-DETECT-12): emit the raw
        # record and a normalized, tenant-keyed event; the anomaly (if any) is
        # published to alerts.raised below.
        record = dict(log)
        record["org_id"] = org_id
        if alert_type == "network":
            send_raw_flow(record)
        else:
            send_raw_log(record)
        send_normalized(
            {
                "tenant_id": org_id,
                "source": log.get("source") or log.get("src_ip") or "unknown",
                "type": alert_type,
                "message": message,
                "anomaly_score": score,
                "is_anomaly": is_anomaly,
                "severity": severity,
                "timestamp": log.get("timestamp"),
                "org_id": org_id,
            }
        )

    alert = {
        "alert_type": alert_type,
        "source_ip": source_ip,
        "severity": severity,
        "score": score,
        "message": message,
        "mitre_tactic": mitre["tactic"],
        "mitre_technique_id": mitre["technique_id"],
        "mitre_technique": mitre["technique"],
        "threat_intel": intel,
    }
    if org_id is not None:
        alert["org_id"] = org_id

    try:
        if is_anomaly:
            alert_row = SecurityAlert(**alert)
            db.add(alert_row)
            db.commit()  # alert durable first; graph indexing is best-effort
            index_alert(db, alert_row)
            db.commit()
            alert["id"] = alert_row.id
            rules = db.query(DetectionRule).filter(DetectionRule.is_active.is_(True)).all()
            respond_to_alert(db, alert, rules)
            db.commit()
            if produce_kafka:
                send_alert({**alert, "org_id": org_id} if org_id is not None else alert)
    finally:
        if uses_own_session:
            db.close()

    return {
        "anomaly_score": score,
        "is_anomaly": is_anomaly,
        "type": alert_type,
        "severity": severity,
        "message": message,
        "fallback": bool(result.get("fallback", False)),
    }


def process_batch(logs: list[dict], filename: str, produce_kafka: bool = True, org_id: Optional[int] = None) -> dict:
    """Scan a full batch of log records and persist both SecurityAlert and
    ScannedAlert evidence rows for any anomaly. Returns a run summary.

    Used by the background scan for uploaded files so upload history is
    preserved in the database instead of an in-memory store.
    """
    db: Session = session_factory()
    threats_detected = 0
    results = []
    try:
        for record in logs[:100]:
            try:
                result = process_log(record, produce_kafka=produce_kafka, db=db, org_id=org_id)
                results.append({"input": record, "result": result})
                if result.get("is_anomaly"):
                    threats_detected += 1
                    db.add(ScannedAlert(
                        filename=filename,
                        threat_type=result.get("type", "system_log"),
                        raw_log=str(record.get("message") or record.get("content") or record)[:2000],
                        risk=result.get("severity", "LOW"),
                        org_id=org_id,
                    ))
            except Exception as row_err:
                results.append({"input": record, "error": str(row_err)})
        db.commit()
    finally:
        db.close()

    return {
        "total_logs": len(logs),
        "threats_detected": threats_detected,
        "results": results,
    }


def get_alert_stats(db: Session) -> dict:
    """Aggregate severity counts and recent activity for the dashboard KPIs."""
    alerts = db.query(SecurityAlert).all()

    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for alert in alerts:
        sev = (alert.severity or "LOW").upper()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    from collections import Counter

    by_type = Counter((a.alert_type or "unknown") for a in alerts)

    recent = sorted(
        alerts,
        key=lambda a: a.created_at or __import__("datetime").datetime.min,
        reverse=True,
    )[:10]

    return {
        "total": len(alerts),
        "critical": severity_counts["CRITICAL"],
        "high": severity_counts["HIGH"],
        "medium": severity_counts["MEDIUM"],
        "low": severity_counts["LOW"],
        "severity_distribution": severity_counts,
        "by_type": dict(by_type),
        "recent": [{"id": a.id, "message": a.message, "severity": a.severity, "created_at": a.created_at.isoformat() if a.created_at else None} for a in recent],
    }


def get_top_threats(db: Session, limit: int = 10) -> list:
    """Return the most common alert messages/patterns."""
    from collections import Counter

    alerts = db.query(SecurityAlert).all()
    counter = Counter((a.message or "Unknown")[:120] for a in alerts)
    return [{"threat": label, "count": count} for label, count in counter.most_common(limit)]
