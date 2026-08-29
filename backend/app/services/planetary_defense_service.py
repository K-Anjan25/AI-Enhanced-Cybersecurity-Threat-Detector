"""Phase 128: Planetary Defense service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.planetary_defense import PlanetaryDefenseGrid, CriticalInfraNode, PlanetaryThreat

def _now():
    return datetime.now(timezone.utc)

def create_grid(db: Session, org_id: int, name: str) -> PlanetaryDefenseGrid:
    grid = PlanetaryDefenseGrid(org_id=org_id, name=name, grid_type="global", coverage_json={"power_grid": 85, "water": 90, "telecom": 88, "finance": 92, "healthcare": 80}, threat_level="elevated", defense_readiness=87.5, status="active")
    db.add(grid)
    db.commit()
    db.refresh(grid)
    # Seed infra nodes
    for infra_type in ["power_grid","water","telecom","finance","healthcare"]:
        node = CriticalInfraNode(grid_id=grid.id, org_id=org_id, node_name=f"{infra_type}-us-east", infra_type=infra_type, location="us-east-1", criticality="critical", security_posture=78.0, status="operational")
        db.add(node)
    db.commit()
    return grid

def list_grids(db: Session, org_id: int) -> List[PlanetaryDefenseGrid]:
    return db.query(PlanetaryDefenseGrid).filter(PlanetaryDefenseGrid.org_id == org_id).all()

def create_threat(db: Session, org_id: int, grid_id: int, threat_name: str, threat_type: str = "nation_state") -> PlanetaryThreat:
    grid = db.query(PlanetaryDefenseGrid).filter(PlanetaryDefenseGrid.id == grid_id, PlanetaryDefenseGrid.org_id == org_id).first()
    if not grid:
        raise ValueError("Grid not found")
    threat = PlanetaryThreat(grid_id=grid_id, org_id=org_id, threat_name=threat_name, threat_type=threat_type, affected_infra=["power_grid","telecom"], impact_score=85.0, mitigation_json={"isolate": True, "backup_power": True}, status="active")
    db.add(threat)
    db.commit()
    db.refresh(threat)
    return threat

def serialize_grid(g: PlanetaryDefenseGrid) -> Dict[str, Any]:
    return {"id": g.id, "name": g.name, "grid_type": g.grid_type, "coverage": g.coverage_json, "threat_level": g.threat_level, "defense_readiness": g.defense_readiness, "status": g.status}
