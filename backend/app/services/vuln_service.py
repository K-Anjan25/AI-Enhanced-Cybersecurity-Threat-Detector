"""Phase 63: Vulnerability management + PT."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.vuln import Vulnerability, VulnScan, PentestFinding
from app.models import SecurityAlert
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


def list_vulns(db: Session, org_id: int, severity: str = None, status: str = None, limit: int = 100) -> List[Vulnerability]:
    q = db.query(Vulnerability).filter(Vulnerability.org_id == org_id)
    if severity:
        q = q.filter(Vulnerability.severity == severity.upper())
    if status:
        q = q.filter(Vulnerability.status == status)
    return q.order_by(Vulnerability.cvss_score.desc().nullslast(), Vulnerability.created_at.desc()).limit(limit).all()


def create_vuln(
    db: Session,
    org_id: int,
    title: str,
    severity: str = "MEDIUM",
    cve_id: str = None,
    cvss_score: float = None,
    affected_asset: str = None,
    description: str = None,
    remediation: str = None,
    discovered_by: str = "scanner",
    extra: Dict[str, Any] = None,
) -> Vulnerability:
    v = Vulnerability(
        org_id=org_id,
        title=title,
        severity=severity.upper(),
        cve_id=cve_id,
        cvss_score=cvss_score,
        affected_asset=affected_asset,
        description=description,
        remediation=remediation,
        discovered_by=discovered_by,
        extra=extra or {},
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def ingest_scan_results(db: Session, org_id: int, scanner_name: str, target: str, results: List[Dict[str, Any]], created_by_user_id: int = None) -> VulnScan:
    """Ingest vuln scanner output (Trivy, Nessus, etc) into Vulnerability table."""
    critical = 0
    high = 0
    for r in results:
        sev = (r.get("severity") or "MEDIUM").upper()
        if sev == "CRITICAL":
            critical += 1
        elif sev == "HIGH":
            high += 1
        # Create vuln if not exists (by cve_id + asset)
        cve = r.get("cve_id") or r.get("id")
        asset = r.get("affected_asset") or target
        existing = None
        if cve:
            existing = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.cve_id == cve, Vulnerability.affected_asset == asset).first()
        if not existing:
            create_vuln(
                db,
                org_id=org_id,
                title=r.get("title") or f"{cve or 'Vuln'} on {asset}",
                severity=sev,
                cve_id=cve,
                cvss_score=r.get("cvss_score") or r.get("cvss"),
                affected_asset=asset,
                description=r.get("description"),
                remediation=r.get("remediation") or r.get("fixed_version"),
                discovered_by=scanner_name,
                extra=r,
            )

    scan = VulnScan(
        org_id=org_id,
        scanner_name=scanner_name,
        target=target,
        status="completed",
        vuln_count=len(results),
        critical_count=critical,
        high_count=high,
        scan_results_json=results[:200],
        completed_at=_now(),
        created_by_user_id=created_by_user_id,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def get_risk_summary(db: Session, org_id: int) -> Dict[str, Any]:
    """Aggregate vuln risk: counts by severity, top assets, correlation with alerts."""
    total = db.query(Vulnerability).filter(Vulnerability.org_id == org_id).count()
    critical = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.severity == "CRITICAL", Vulnerability.status == "open").count()
    high = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.severity == "HIGH", Vulnerability.status == "open").count()
    medium = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.severity == "MEDIUM", Vulnerability.status == "open").count()
    low = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.severity == "LOW", Vulnerability.status == "open").count()

    # Top affected assets
    top_assets = (
        db.query(Vulnerability.affected_asset, func.count(Vulnerability.id).label("cnt"))
        .filter(Vulnerability.org_id == org_id, Vulnerability.status == "open")
        .group_by(Vulnerability.affected_asset)
        .order_by(func.count(Vulnerability.id).desc())
        .limit(10)
        .all()
    )

    # Correlation: vulns with related alerts
    correlated = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.related_alert_id.isnot(None)).count()

    # Calculate risk score 0-100
    risk_score = min(100, (critical * 10 + high * 5 + medium * 2 + low * 0.5))

    return {
        "org_id": org_id,
        "total_vulns": total,
        "open_by_severity": {"critical": critical, "high": high, "medium": medium, "low": low},
        "risk_score": risk_score,
        "risk_band": "CRITICAL" if risk_score >= 80 else "HIGH" if risk_score >= 50 else "MEDIUM" if risk_score >= 20 else "LOW",
        "top_assets": [{"asset": a[0], "count": a[1]} for a in top_assets if a[0]],
        "correlated_with_alerts": correlated,
        "threshold": getattr(settings, "VULN_RISK_THRESHOLD", 7.0),
    }


def list_scans(db: Session, org_id: int, limit: int = 20) -> List[VulnScan]:
    return db.query(VulnScan).filter(VulnScan.org_id == org_id).order_by(VulnScan.started_at.desc()).limit(limit).all()


def serialize_vuln(v: Vulnerability) -> Dict[str, Any]:
    return {
        "id": v.id,
        "cve_id": v.cve_id,
        "title": v.title,
        "severity": v.severity,
        "cvss_score": v.cvss_score,
        "affected_asset": v.affected_asset,
        "affected_component": v.affected_component,
        "status": v.status,
        "discovered_by": v.discovered_by,
        "remediation": v.remediation,
        "first_seen_at": v.first_seen_at.isoformat() if v.first_seen_at else None,
        "last_seen_at": v.last_seen_at.isoformat() if v.last_seen_at else None,
    }


def serialize_scan(s: VulnScan) -> Dict[str, Any]:
    return {
        "id": s.id,
        "scanner_name": s.scanner_name,
        "target": s.target,
        "status": s.status,
        "vuln_count": s.vuln_count,
        "critical_count": s.critical_count,
        "high_count": s.high_count,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }
