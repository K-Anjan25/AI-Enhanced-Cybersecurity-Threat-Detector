"""Phase 145: Void Defense service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.void_defense import VoidSector, VoidEntity, VoidShield

def _now():
    return datetime.now(timezone.utc)

def create_sector(db: Session, org_id: int, name: str) -> VoidSector:
    sector = VoidSector(org_id=org_id, name=name, sector_coordinates={"x": 0, "y": 0, "z": -1000, "dark_dimension": 1}, void_energy=75.0, dark_matter_density=0.27, threat_level="HIGH", status="monitored")
    db.add(sector)
    db.commit()
    db.refresh(sector)
    shield = VoidShield(sector_id=sector.id, org_id=org_id, shield_type="dark_energy_barrier", strength=99.0, config_json={"exotic_matter": True}, status="active")
    db.add(shield)
    db.commit()
    return sector

def list_sectors(db: Session, org_id: int) -> List[VoidSector]:
    return db.query(VoidSector).filter(VoidSector.org_id == org_id).all()

def spawn_entity(db: Session, org_id: int, sector_id: int, entity_type: str = "void_predator") -> VoidEntity:
    sector = db.query(VoidSector).filter(VoidSector.id == sector_id, VoidSector.org_id == org_id).first()
    if not sector:
        raise ValueError("Sector not found")
    entity = VoidEntity(sector_id=sector_id, org_id=org_id, entity_type=entity_type, description=f"{entity_type} emerging from dark universe void", power_level=85.0, status="contained")
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity

def serialize_sector(s: VoidSector) -> Dict[str, Any]:
    return {"id": s.id, "name": s.name, "sector_coordinates": s.sector_coordinates, "void_energy": s.void_energy, "dark_matter_density": s.dark_matter_density, "threat_level": s.threat_level, "status": s.status}
