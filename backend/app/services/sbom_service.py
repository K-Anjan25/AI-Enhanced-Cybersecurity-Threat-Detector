"""Phase 66: SBOM + supply chain."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.sbom import SBOM, Dependency, SupplyChainRisk
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


def parse_cyclonedx(db: Session, org_id: int, sbom_json: Dict[str, Any], name: str, source: str = None, created_by_user_id: int = None) -> SBOM:
    """Parse CycloneDX SBOM, create dependencies, check risks."""
    components = sbom_json.get("components", []) if isinstance(sbom_json, dict) else []
    if not components and "bom" in sbom_json:
        components = sbom_json.get("bom", {}).get("components", [])

    sbom = SBOM(
        org_id=org_id,
        name=name,
        version=sbom_json.get("version") or sbom_json.get("metadata", {}).get("version") or "1.0",
        format="cyclonedx",
        source=source,
        component_count=len(components),
        sbom_json=sbom_json,
        created_by_user_id=created_by_user_id,
    )
    db.add(sbom)
    db.commit()
    db.refresh(sbom)

    vuln_count = 0
    for comp in components[: getattr(settings, "SBOM_MAX_DEPENDENCIES", 10000)]:
        if not isinstance(comp, dict):
            continue
        comp_name = comp.get("name") or comp.get("purl") or "unknown"
        comp_version = comp.get("version")
        purl = comp.get("purl")
        license_info = None
        licenses = comp.get("licenses", [])
        if licenses and isinstance(licenses, list) and licenses[0].get("license", {}).get("id"):
            license_info = licenses[0]["license"]["id"]

        dep = Dependency(
            org_id=org_id,
            sbom_id=sbom.id,
            name=comp_name,
            version=comp_version,
            purl=purl,
            license=license_info,
            extra=comp,
        )
        db.add(dep)
        db.commit()
        db.refresh(dep)

        # Check for known vulnerable packages (simplified)
        vuln_keywords = ["log4j", "openssl", "lodash"]
        if any(kw in comp_name.lower() for kw in vuln_keywords):
            risk = SupplyChainRisk(
                org_id=org_id,
                dependency_id=dep.id,
                sbom_id=sbom.id,
                risk_type="vulnerable_dependency",
                severity="HIGH" if "log4j" in comp_name.lower() else "MEDIUM",
                description=f"Dependency {comp_name} may contain known vulnerabilities",
                status="open",
            )
            db.add(risk)
            vuln_count += 1
            dep.vuln_count = 1
            dep.risk_score = 7.5
            db.commit()

    sbom.vuln_count = vuln_count
    db.commit()
    db.refresh(sbom)
    return sbom


def list_sboms(db: Session, org_id: int) -> List[SBOM]:
    return db.query(SBOM).filter(SBOM.org_id == org_id).order_by(SBOM.created_at.desc()).all()


def list_dependencies(db: Session, org_id: int, sbom_id: int = None) -> List[Dependency]:
    q = db.query(Dependency).filter(Dependency.org_id == org_id)
    if sbom_id:
        q = q.filter(Dependency.sbom_id == sbom_id)
    return q.limit(200).all()


def list_risks(db: Session, org_id: int, severity: str = None) -> List[SupplyChainRisk]:
    q = db.query(SupplyChainRisk).filter(SupplyChainRisk.org_id == org_id, SupplyChainRisk.status == "open")
    if severity:
        q = q.filter(SupplyChainRisk.severity == severity.upper())
    return q.order_by(SupplyChainRisk.created_at.desc()).limit(100).all()


def serialize_sbom(s: SBOM) -> Dict[str, Any]:
    return {"id": s.id, "name": s.name, "version": s.version, "format": s.format, "source": s.source, "component_count": s.component_count, "vuln_count": s.vuln_count, "created_at": s.created_at.isoformat() if s.created_at else None}


def serialize_dep(d: Dependency) -> Dict[str, Any]:
    return {"id": d.id, "sbom_id": d.sbom_id, "name": d.name, "version": d.version, "purl": d.purl, "license": d.license, "risk_score": d.risk_score, "vuln_count": d.vuln_count}
