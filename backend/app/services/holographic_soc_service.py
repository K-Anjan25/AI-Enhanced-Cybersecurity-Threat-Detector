"""Phase 125: Holographic SOC service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.holographic_soc import HolographicDisplay, Hologram, HoloInteraction

def _now():
    return datetime.now(timezone.utc)

def create_display(db: Session, org_id: int, name: str, display_type: str = "volumetric") -> HolographicDisplay:
    disp = HolographicDisplay(org_id=org_id, display_name=name, display_type=display_type, resolution="8K volumetric", size_inches=85.0, location="SOC War Room", status="active")
    db.add(disp)
    db.commit()
    db.refresh(disp)
    return disp

def list_displays(db: Session, org_id: int) -> List[HolographicDisplay]:
    return db.query(HolographicDisplay).filter(HolographicDisplay.org_id == org_id).all()

def create_hologram(db: Session, org_id: int, display_id: int, holo_type: str = "threat_globe") -> Hologram:
    disp = db.query(HolographicDisplay).filter(HolographicDisplay.id == display_id, HolographicDisplay.org_id == org_id).first()
    if not disp:
        raise ValueError("Display not found")
    content_map = {
        "threat_globe": {"globe": "earth", "threats": [{"lat": 37.7, "lon": -122.4, "severity": "HIGH"}]},
        "network_graph": {"nodes": 100, "edges": 250},
        "attack_path": {"path": ["internet","dmz","prod","crown_jewel"]}
    }
    holo = Hologram(display_id=display_id, org_id=org_id, hologram_type=holo_type, content_json=content_map.get(holo_type, {}), position_json={"x": 0, "y": 1.5, "z": -2, "rotation": 0, "scale": 1.0}, is_interactive=True)
    db.add(holo)
    db.commit()
    db.refresh(holo)
    return holo

def serialize_display(d: HolographicDisplay) -> Dict[str, Any]:
    return {"id": d.id, "display_name": d.display_name, "display_type": d.display_type, "resolution": d.resolution, "size_inches": d.size_inches, "location": d.location, "status": d.status}

def serialize_hologram(h: Hologram) -> Dict[str, Any]:
    return {"id": h.id, "display_id": h.display_id, "hologram_type": h.hologram_type, "content": h.content_json, "position": h.position_json, "is_interactive": h.is_interactive}
