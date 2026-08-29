"""Phase 56: ATT&CK navigator + timeline export + actor attribution."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import attack_service

router = APIRouter(prefix="/attack", tags=["ATT&CK (Phase 56)"])


class ActorCreate(BaseModel):
    name: str
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    techniques: Optional[List[str]] = None
    country: Optional[str] = None


@router.get("/matrix")
def get_matrix(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return attack_service.get_attack_matrix()


@router.get("/heatmap")
def get_heatmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    return attack_service.get_attack_heatmap(db, org_id=current_user.org_id)


@router.post("/attribute")
def attribute_actor(
    techniques: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    result = attack_service.attribute_actor(db, org_id=current_user.org_id, techniques=techniques)
    return result


@router.get("/actors")
def list_actors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    rows = attack_service.list_threat_actors(db, org_id=current_user.org_id)
    return [attack_service.serialize_actor(a) for a in rows]


@router.post("/actors", status_code=201)
def create_actor(
    payload: ActorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    actor = attack_service.create_threat_actor(
        db,
        org_id=current_user.org_id,
        name=payload.name,
        description=payload.description,
        aliases=payload.aliases,
        techniques=payload.techniques,
        country=payload.country,
    )
    return attack_service.serialize_actor(actor)


@router.get("/timeline/{case_id}/export")
def export_timeline(
    case_id: int,
    format: str = "json",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    from app.services import case_service, incident_timeline_service

    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get ATT&CK context
    techniques = case.mitre_techniques if hasattr(case, "mitre_techniques") and case.mitre_techniques else []

    # Build timeline from case events + alert chain
    timeline_events = []
    if hasattr(case, "events") and case.events:
        for ev in case.events:
            timeline_events.append(
                {
                    "timestamp": ev.created_at.isoformat() if ev.created_at else None,
                    "type": "alert",
                    "title": ev.title if hasattr(ev, "title") else str(ev.id),
                    "technique_id": ev.mitre_technique_id if hasattr(ev, "mitre_technique_id") else None,
                }
            )

    if format == "attack-navigator":
        # Format compatible with MITRE ATT&CK Navigator layer
        heatmap = attack_service.get_attack_heatmap(db, org_id=current_user.org_id)
        layer = {
            "name": f"Case {case_id} ATT&CK",
            "versions": {"attack": "13", "navigator": "4.9.1", "layer": "4.5"},
            "domain": "enterprise-attack",
            "techniques": [{"techniqueID": h["technique_id"], "score": h["count"], "color": "#ff6666" if h["count"] > 5 else "#ffcc00"} for h in heatmap.get("heatmap", [])],
        }
        return layer

    return {"case_id": case_id, "techniques": techniques, "timeline": timeline_events, "export_format": format}
