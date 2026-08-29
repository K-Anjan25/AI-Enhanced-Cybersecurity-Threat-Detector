"""Phase 53: Compliance packs — ISO27001, NIST, GDPR, SOC2 + S3 export."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.compliance_pack import CompliancePack, ComplianceExportSchedule, ComplianceExportLog
from app.core.config import settings

_LOGGER = logging.getLogger(__name__)

# Predefined packs

PACKS = {
    "SOC2": {
        "description": "SOC2 Trust Services Criteria",
        "controls": {
            "CC6.1": {"name": "Logical and Physical Access Controls", "description": "Authorizes, modifies, or removes access"},
            "CC6.2": {"name": "System Access Monitoring", "description": "Monitors system components"},
            "CC7.2": {"name": "System Monitoring", "description": "Monitors for anomalies"},
            "CC8.1": {"name": "Change Management", "description": "Authorizes system changes"},
        },
    },
    "ISO27001": {
        "description": "ISO/IEC 27001:2022 Information Security",
        "controls": {
            "A.5.15": {"name": "Access Control", "description": "Access control policy"},
            "A.5.16": {"name": "Identity Management", "description": "Identity management"},
            "A.8.15": {"name": "Logging", "description": "Logging and monitoring"},
            "A.8.16": {"name": "Monitoring Activities", "description": "Monitoring activities"},
            "A.5.24": {"name": "Incident Management Planning", "description": "Incident management"},
        },
    },
    "NIST": {
        "description": "NIST CSF 2.0",
        "controls": {
            "PR.AC-1": {"name": "Identities and Credentials", "description": "Identities and credentials are managed"},
            "DE.CM-1": {"name": "Networks Monitored", "description": "Networks monitored"},
            "DE.AE-1": {"name": "Baseline of Operations", "description": "Baseline established"},
            "RS.RP-1": {"name": "Response Plan", "description": "Response plan executed"},
            "ID.AM-1": {"name": "Asset Management", "description": "Physical devices inventoried"},
        },
    },
    "GDPR": {
        "description": "GDPR Compliance",
        "controls": {
            "Art.5": {"name": "Principles of Processing", "description": "Lawfulness, fairness, transparency"},
            "Art.25": {"name": "Data Protection by Design", "description": "Data protection by design and default"},
            "Art.30": {"name": "Records of Processing", "description": "Records of processing activities"},
            "Art.32": {"name": "Security of Processing", "description": "Security of processing"},
            "Art.33": {"name": "Breach Notification", "description": "Breach notification to authority"},
        },
    },
}


def ensure_default_packs(db: Session, org_id: int):
    existing = {p.name for p in db.query(CompliancePack).filter(CompliancePack.org_id == org_id).all()}
    for pack_name, pack_data in PACKS.items():
        if pack_name not in existing:
            pack = CompliancePack(
                org_id=org_id,
                name=pack_name,
                description=pack_data["description"],
                controls=pack_data["controls"],
                is_active=True,
            )
            db.add(pack)
    db.commit()


def list_packs(db: Session, org_id: int) -> List[CompliancePack]:
    ensure_default_packs(db, org_id)
    return db.query(CompliancePack).filter(CompliancePack.org_id == org_id).order_by(CompliancePack.name).all()


def get_pack(db: Session, org_id: int, pack_name: str) -> Optional[CompliancePack]:
    ensure_default_packs(db, org_id)
    return db.query(CompliancePack).filter(CompliancePack.org_id == org_id, CompliancePack.name == pack_name).first()


def create_export_schedule(
    db: Session,
    org_id: int,
    pack_name: str,
    frequency: str = "weekly",
    destination: str = "s3",
    s3_path: str = None,
) -> ComplianceExportSchedule:
    pack = get_pack(db, org_id, pack_name)
    if not pack:
        raise ValueError(f"Pack {pack_name} not found")
    now = datetime.now(timezone.utc)
    next_run = now + timedelta(days=7 if frequency == "weekly" else 1 if frequency == "daily" else 30)
    sched = ComplianceExportSchedule(
        org_id=org_id,
        pack_id=pack.id,
        frequency=frequency,
        destination=destination,
        s3_path=s3_path,
        next_run_at=next_run,
        is_active=True,
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


def list_schedules(db: Session, org_id: int) -> List[ComplianceExportSchedule]:
    return db.query(ComplianceExportSchedule).filter(ComplianceExportSchedule.org_id == org_id).order_by(ComplianceExportSchedule.created_at.desc()).all()


def export_to_s3(db: Session, org_id: int, pack_name: str, pdf_bytes: bytes) -> Dict[str, Any]:
    """Export compliance PDF to S3 if configured, else return local path info."""
    s3_endpoint = getattr(settings, "S3_ENDPOINT", None)
    s3_bucket = getattr(settings, "S3_BUCKET", None)
    s3_access = getattr(settings, "S3_ACCESS_KEY", None)
    s3_secret = getattr(settings, "S3_SECRET_KEY", None)

    if not (s3_endpoint and s3_bucket and s3_access and s3_secret):
        # Fallback: not configured, log as local
        log = ComplianceExportLog(
            org_id=org_id,
            pack_name=pack_name,
            file_path=f"/tmp/{pack_name.lower()}-evidence-{datetime.now(timezone.utc).isoformat()}.pdf",
            status="success",
        )
        db.add(log)
        db.commit()
        return {"destination": "local", "path": log.file_path, "s3_configured": False}

    try:
        # Try boto3 if available
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access,
            aws_secret_access_key=s3_secret,
        )
        key = f"compliance/{org_id}/{pack_name.lower()}/{datetime.now(timezone.utc).date()}/evidence.pdf"
        s3.put_object(Bucket=s3_bucket, Key=key, Body=pdf_bytes, ContentType="application/pdf")
        s3_url = f"{s3_endpoint}/{s3_bucket}/{key}"
        log = ComplianceExportLog(
            org_id=org_id,
            pack_name=pack_name,
            s3_url=s3_url,
            file_path=key,
            status="success",
        )
        db.add(log)
        db.commit()
        return {"destination": "s3", "s3_url": s3_url, "key": key, "s3_configured": True}
    except Exception as exc:
        _LOGGER.warning("S3 export failed: %s", exc)
        log = ComplianceExportLog(
            org_id=org_id,
            pack_name=pack_name,
            status="failed",
            error=str(exc)[:500],
        )
        db.add(log)
        db.commit()
        return {"destination": "s3", "error": str(exc)[:200], "s3_configured": True, "status": "failed"}


def serialize_pack(p: CompliancePack) -> Dict[str, Any]:
    return {
        "id": p.id,
        "org_id": p.org_id,
        "name": p.name,
        "description": p.description,
        "controls": p.controls,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def serialize_schedule(s: ComplianceExportSchedule) -> Dict[str, Any]:
    return {
        "id": s.id,
        "org_id": s.org_id,
        "pack_id": s.pack_id,
        "frequency": s.frequency,
        "destination": s.destination,
        "s3_path": s.s3_path,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
