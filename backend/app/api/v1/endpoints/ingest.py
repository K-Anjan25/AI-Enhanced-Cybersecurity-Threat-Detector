from datetime import datetime, timezone
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
import json
import csv
import io
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.services import alert_service
from app.services.alert_service import process_batch
from app.models import SecurityAlert, ScannedAlert, ScanBatch, User
from app.utils.helpers import severity_to_score

router = APIRouter()


def _run_background_scan(batch_id: int, records: list[dict], filename: str, org_id: int | None = None):
    """Scan an uploaded log batch in the background and persist the result."""
    db: Session = alert_service.session_factory()
    try:
        batch = db.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if not batch:
            return
        batch.status = "processing"
        db.commit()

        summary = process_batch(records, filename, produce_kafka=settings.ENABLE_KAFKA, org_id=org_id)

        batch.total_logs = summary["total_logs"]
        batch.threats_detected = summary["threats_detected"]
        batch.status = "completed"
        batch.message = "Scan completed"
        db.commit()
    except Exception as exc:  # pragma: no cover - error path for background task
        batch = db.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if batch:
            batch.status = "failed"
            batch.message = str(exc)
            db.commit()
    finally:
        db.close()


@router.post("/upload-logs")
async def upload_logs(
    log_file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        contents = await log_file.read()
        text_content = contents.decode("utf-8", errors="ignore")

        # Check if file is JSON, CSV, or raw plain-text logs
        if log_file.filename.endswith(".json"):
            records = json.loads(text_content)
            if not isinstance(records, list):
                records = [records]
        elif log_file.filename.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(text_content))
            records = [row for row in reader]
        else:
            records = [{"message": line, "level": "INFO"} for line in text_content.splitlines() if line.strip()]

        records = records[:100]  # Limit to first 100 rows for safe payload processing

        batch = ScanBatch(
            filename=log_file.filename,
            total_logs=len(records),
            threats_detected=0,
            status="pending",
            org_id=current_user.org_id,
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        if background_tasks is not None:
            background_tasks.add_task(_run_background_scan, batch.id, records, log_file.filename, batch.org_id)

        return {
            "message": "Logs uploaded and queued for scanning.",
            "batch_id": batch.id,
            "filename": log_file.filename,
            "totalLogsParsed": len(records),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/uploads/{batch_id}")
def get_upload_batch_status(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the status and result summary of a background scan batch."""
    batch = db.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Scan batch not found")
    # Tenant scoping: batches from another org are invisible (legacy NULL-org
    # batches from before tenancy remain visible to authenticated users).
    if batch.org_id is not None and batch.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Scan batch not found")

    return {
        "batch": {
            "id": batch.id,
            "filename": batch.filename,
            "total_logs": batch.total_logs,
            "threats_detected": batch.threats_detected,
            "status": batch.status,
            "message": batch.message,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        }
    }

@router.post("/save-scanned-alerts")
def save_scanned_alerts(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    threats = payload.get("threats")
    if not isinstance(threats, list):
        raise HTTPException(status_code=400, detail="A threat list is required.")

    saved_alerts = []
    for threat in threats:
        if not isinstance(threat, dict):
            continue

        rule_name = threat.get("ruleName") or "Detected Threat"
        severity = (threat.get("severity") or "LOW").upper()
        details = threat.get("details") or "Threat detected from uploaded log."
        raw_log = threat.get("rawLog") or details or ""

        alert_message = f"{rule_name}: {details}"
        score = severity_to_score(severity)

        security_alert = SecurityAlert(
            alert_type="scanned_log",
            source_ip=None,
            source="upload",
            severity=severity,
            score=score,
            message=alert_message,
            org_id=current_user.org_id,
        )
        db.add(security_alert)
        db.flush()

        scanned_alert = ScannedAlert(
            filename=payload.get("filename") or "uploaded_log",
            threat_type=rule_name,
            raw_log=raw_log,
            risk=severity,
        )
        db.add(scanned_alert)
        saved_alerts.append(security_alert)

    db.commit()

    return {
        "message": "Scanned threats saved as alerts.",
        "savedCount": len(saved_alerts),
        "alerts": [
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "source_ip": alert.source_ip,
                "source": alert.source,
                "severity": alert.severity,
                "score": alert.score,
                "message": alert.message,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
            for alert in saved_alerts
        ],
    }


@router.get("/logs/history")
def get_log_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns persistent upload/scan history from the database (survives restarts).
    Tenant-scoped: own-org batches plus legacy NULL-org rows.
    """
    batches = (
        db.query(ScanBatch)
        .filter(or_(ScanBatch.org_id == current_user.org_id, ScanBatch.org_id.is_(None)))
        .order_by(ScanBatch.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "logs": [
            {
                "filename": b.filename,
                "batch_id": b.id,
                "totalLogsParsed": b.total_logs,
                "threatsDetected": b.threats_detected,
                "status": b.status,
                "timestamp": b.created_at.isoformat() if b.created_at else None,
            }
            for b in batches
        ]
    }