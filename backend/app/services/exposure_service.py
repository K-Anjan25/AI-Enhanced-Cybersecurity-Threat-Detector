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
    """Discover internet-facing surface from Certificate Transparency.

    This used to invent four exposures against 203.0.113.x — including an
    "admin panel exposed without auth" — for any domain asked about. That was
    the most damaging mock in the codebase: attack-path search treats open
    exposures as the attacker's way in, so fabricated exposures produced
    fabricated attack paths against real assets.

    CT logs are a genuine source of externally-visible hostnames: every
    publicly-trusted certificate is logged, so subdomains with a cert are
    demonstrably published. We record those as discovered hostnames at LOW
    severity — a name being visible is a fact; calling it "vulnerable" would
    require a port scan we do not perform.

    Returns an empty list when CT is disabled or the lookup fails. An empty
    result means "nothing discovered", never "nothing exists".
    """
    if not domain:
        return []

    from app.services import ct_log_client

    if not ct_log_client.is_enabled():
        return []

    result = ct_log_client.lookup_domain(domain)
    if not result.ok or not result.certificates:
        return []

    domain_obj = (
        db.query(ASM_Domain)
        .filter(ASM_Domain.org_id == org_id, ASM_Domain.domain == domain)
        .first()
    )
    if not domain_obj:
        domain_obj = add_domain(db, org_id, domain, discovery_method="certificate_transparency")

    # Collect every distinct hostname the certificates actually cover.
    hostnames: List[str] = []
    for cert in result.certificates:
        for name in cert.get("names", []):
            if name and name not in hostnames:
                hostnames.append(name)

    existing = {
        e.name
        for e in db.query(ASM_AssetExposure)
        .filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.status == "open")
        .all()
    }

    exposures: List[ASM_AssetExposure] = []
    for hostname in hostnames:
        if hostname in existing:
            continue
        exp = ASM_AssetExposure(
            org_id=org_id,
            domain_id=domain_obj.id,
            asset_type="host",
            name=hostname,
            port=443,
            service="https",
            exposure_type="published_hostname",
            severity="LOW",
            description=(
                f"{hostname} has a publicly logged TLS certificate, so it is "
                "advertised to the internet. Reachability and open ports are NOT "
                "checked — this records visibility, not vulnerability."
            ),
            evidence_json={
                "source": "certificate_transparency",
                "issuers": result.issuers,
                "first_seen": result.first_seen,
                "port_scanned": False,
            },
            status="open",
        )
        db.add(exp)
        exposures.append(exp)

    db.commit()
    for e in exposures:
        db.refresh(e)
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


_EXPOSURE_STATUSES = ("open", "fixed", "ignored")


def set_exposure_status(
    db: Session, org_id: int, exposure_id: int, status: str, note: str = None
) -> ASM_AssetExposure:
    """Close an exposure, or mark it as not a real finding.

    Attack-path search treats every *open* exposure as a way in, so an entry
    that is wrong — a hostname that resolves nowhere, a service that was
    decommissioned — keeps generating routes to crown jewels until someone can
    say so. Until now nothing could: the model had `fixed` and `ignored`
    states and no code path set them.
    """
    if status not in _EXPOSURE_STATUSES:
        raise ValueError(
            f"Unknown status {status!r}. Expected one of: {', '.join(_EXPOSURE_STATUSES)}."
        )

    exposure = (
        db.query(ASM_AssetExposure)
        .filter(ASM_AssetExposure.id == exposure_id, ASM_AssetExposure.org_id == org_id)
        .first()
    )
    if not exposure:
        raise ValueError("Exposure not found")

    exposure.status = status
    if note:
        # Keep the operator's reasoning next to the evidence that prompted it,
        # so a later reader can tell why this was dismissed.
        evidence = dict(exposure.evidence_json or {})
        evidence["status_note"] = note
        evidence["status_set_at"] = _now().isoformat()
        exposure.evidence_json = evidence
    db.commit()
    db.refresh(exposure)
    return exposure


def get_exposure_summary(db: Session, org_id: int) -> Dict[str, Any]:
    total = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id).count()
    open_exp = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.status == "open").count()
    high = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.severity == "HIGH", ASM_AssetExposure.status == "open").count()
    critical = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.severity == "CRITICAL", ASM_AssetExposure.status == "open").count()
    expired_certs = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.exposure_type == "expired_cert", ASM_AssetExposure.status == "open").count()

    # `risk_score: critical*20 + high*10` was presented as a 0-100 score but is
    # only a weighted count wearing a percentage's clothes — three criticals
    # and nothing else reads as "60% at risk", which means nothing. The counts
    # are the honest version, and the caller can weight them if it wants to.
    return {
        "total_exposures": total,
        "open_exposures": open_exp,
        "high": high,
        "critical": critical,
        "expired_certs": expired_certs,
    }


def serialize_exposure(e: ASM_AssetExposure) -> Dict[str, Any]:
    return {"id": e.id, "name": e.name, "ip_address": e.ip_address, "port": e.port, "service": e.service, "exposure_type": e.exposure_type, "severity": e.severity, "description": e.description, "evidence": e.evidence_json, "status": e.status, "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else None, "last_seen_at": e.last_seen_at.isoformat() if e.last_seen_at else None}


def serialize_finding(f: ExposureFinding) -> Dict[str, Any]:
    return {"id": f.id, "exposure_id": f.exposure_id, "title": f.title, "finding_type": f.finding_type, "severity": f.severity, "description": f.description, "remediation": f.remediation, "status": f.status}
