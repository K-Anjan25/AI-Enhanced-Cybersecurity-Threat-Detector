"""Phase 87: Exposure Management (ASM) service."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.exposure import ASM_Domain, ASM_AssetExposure, ASM_Certificate, ExposureFinding


def _now():
    return datetime.now(timezone.utc)


def add_domain(db: Session, org_id: int, domain: str, discovery_method: str = "manual") -> ASM_Domain:
    d = ASM_Domain(org_id=org_id, domain=domain, discovery_method=discovery_method, is_verified=False)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def list_domains(db: Session, org_id: int) -> List[ASM_Domain]:
    return db.query(ASM_Domain).filter(ASM_Domain.org_id == org_id).order_by(ASM_Domain.created_at.desc()).all()


def discover_exposures(db: Session, org_id: int, domain: str = None) -> List[ASM_AssetExposure]:
    """Mock ASM discovery - in real would query Shodan, Censys, cert transparency."""
    exposures = []
    # Mock exposures for demo
    mock_data = [
        {"name": f"{domain or 'example.com'}", "ip_address": "203.0.113.10", "port": 443, "service": "https", "exposure_type": "open_port", "severity": "LOW", "description": "HTTPS open - expected"},
        {"name": f"{domain or 'example.com'}", "ip_address": "203.0.113.10", "port": 22, "service": "ssh", "exposure_type": "open_port", "severity": "MEDIUM", "description": "SSH exposed to internet - review"},
        {"name": f"admin.{domain or 'example.com'}", "ip_address": "203.0.113.11", "port": 8080, "service": "http", "exposure_type": "exposed_service", "severity": "HIGH", "description": "Admin panel exposed without auth"},
        {"name": f"{domain or 'example.com'}", "ip_address": "203.0.113.10", "port": 443, "service": "https", "exposure_type": "expired_cert", "severity": "MEDIUM", "description": "Certificate expires in 7 days", "evidence": {"cert_expiry": (_now() + timedelta(days=7)).isoformat()}},
    ]

    domain_obj = None
    if domain:
        domain_obj = db.query(ASM_Domain).filter(ASM_Domain.org_id == org_id, ASM_Domain.domain == domain).first()
        if not domain_obj:
            domain_obj = add_domain(db, org_id, domain)

    for mock in mock_data:
        exp = ASM_AssetExposure(
            org_id=org_id,
            domain_id=domain_obj.id if domain_obj else None,
            asset_type="host",
            name=mock["name"],
            ip_address=mock["ip_address"],
            port=mock["port"],
            service=mock["service"],
            exposure_type=mock["exposure_type"],
            severity=mock["severity"],
            description=mock["description"],
            evidence_json=mock.get("evidence", {}),
        )
        db.add(exp)
        exposures.append(exp)
    db.commit()
    for e in exposures:
        db.refresh(e)

    # Create findings for HIGH
    for exp in exposures:
        if exp.severity in ("HIGH", "CRITICAL"):
            finding = ExposureFinding(org_id=org_id, exposure_id=exp.id, title=f"{exp.exposure_type} on {exp.name}:{exp.port}", finding_type=exp.exposure_type, severity=exp.severity, description=exp.description, remediation="Restrict access, add WAF, or close port")
            db.add(finding)
    db.commit()

    return exposures


def list_exposures(db: Session, org_id: int, severity: str = None, status: str = "open") -> List[ASM_AssetExposure]:
    q = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id)
    if severity:
        q = q.filter(ASM_AssetExposure.severity == severity.upper())
    if status:
        q = q.filter(ASM_AssetExposure.status == status)
    return q.order_by(ASM_AssetExposure.severity.desc()).limit(100).all()


def list_findings(db: Session, org_id: int) -> List[ExposureFinding]:
    return db.query(ExposureFinding).filter(ExposureFinding.org_id == org_id, ExposureFinding.status == "open").order_by(ExposureFinding.severity.desc()).limit(50).all()


def get_exposure_summary(db: Session, org_id: int) -> Dict[str, Any]:
    total = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id).count()
    open_exp = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.status == "open").count()
    high = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.severity == "HIGH", ASM_AssetExposure.status == "open").count()
    critical = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.severity == "CRITICAL", ASM_AssetExposure.status == "open").count()
    expired_certs = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.exposure_type == "expired_cert", ASM_AssetExposure.status == "open").count()

    return {"total_exposures": total, "open_exposures": open_exp, "high": high, "critical": critical, "expired_certs": expired_certs, "risk_score": min(100, critical*20 + high*10)}


def serialize_exposure(e: ASM_AssetExposure) -> Dict[str, Any]:
    return {"id": e.id, "name": e.name, "ip_address": e.ip_address, "port": e.port, "service": e.service, "exposure_type": e.exposure_type, "severity": e.severity, "description": e.description, "evidence": e.evidence_json, "status": e.status, "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else None}


def serialize_finding(f: ExposureFinding) -> Dict[str, Any]:
    return {"id": f.id, "exposure_id": f.exposure_id, "title": f.title, "finding_type": f.finding_type, "severity": f.severity, "description": f.description, "remediation": f.remediation, "status": f.status}
