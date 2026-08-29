"""Phase 93: Attack Path Analysis service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.attack_path import AttackPath, AttackPathFinding
from app.models.risk_based import Asset
from app.models.exposure import ASM_AssetExposure

def _now():
    return datetime.now(timezone.utc)

def analyze_paths(db: Session, org_id: int) -> List[AttackPath]:
    """Analyze attack paths from internet to crown jewels."""
    # Get crown jewels (criticality 5)
    crown_jewels = db.query(Asset).filter(Asset.org_id == org_id, Asset.criticality >= 5).all()
    exposures = db.query(ASM_AssetExposure).filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.status == "open").all()

    paths = []
    for jewel in crown_jewels[:3]:
        # Mock path: internet -> exposed asset -> jewel
        # Find exposure that could lead to jewel
        path_nodes = []
        if exposures:
            exp = exposures[0]
            path_nodes = [
                {"type": "internet", "name": "Internet", "cost": 0},
                {"type": "exposure", "exposure_id": exp.id, "name": f"{exp.name}:{exp.port} {exp.exposure_type}", "technique_id": "T1190", "cost": 2},
                {"type": "asset", "asset_id": jewel.id, "name": jewel.name, "criticality": jewel.criticality, "cost": 5},
            ]
            risk_score = 75.0
        else:
            path_nodes = [{"type": "internet", "name": "Internet"}, {"type": "asset", "asset_id": jewel.id, "name": jewel.name}]
            risk_score = 30.0

        existing = db.query(AttackPath).filter(AttackPath.org_id == org_id, AttackPath.crown_jewel_asset_id == jewel.id).first()
        if existing:
            existing.path_json = path_nodes
            existing.risk_score = risk_score
            db.commit()
            paths.append(existing)
        else:
            ap = AttackPath(org_id=org_id, name=f"Path to {jewel.name}", description=f"Internet to crown jewel {jewel.name} via exposures", path_json=path_nodes, risk_score=risk_score, path_type="internet_to_crown_jewel", crown_jewel_asset_id=jewel.id, status="active")
            db.add(ap)
            db.commit()
            db.refresh(ap)
            paths.append(ap)

            # Create choke point finding
            if exposures:
                finding = AttackPathFinding(org_id=org_id, path_id=ap.id, title=f"Choke point: fix {exposures[0].name}:{exposures[0].port}", choke_point_exposure_id=exposures[0].id, choke_point_asset_id=jewel.id, severity="HIGH", remediation=f"Close {exposures[0].port} or restrict access to {exposures[0].name}")
                db.add(finding)
                db.commit()

    return paths

def list_paths(db: Session, org_id: int) -> List[AttackPath]:
    return db.query(AttackPath).filter(AttackPath.org_id == org_id, AttackPath.status == "active").order_by(AttackPath.risk_score.desc()).all()

def serialize_path(p: AttackPath) -> Dict[str, Any]:
    return {"id": p.id, "name": p.name, "description": p.description, "path": p.path_json, "risk_score": p.risk_score, "path_type": p.path_type, "crown_jewel_asset_id": p.crown_jewel_asset_id, "status": p.status, "created_at": p.created_at.isoformat() if p.created_at else None}
