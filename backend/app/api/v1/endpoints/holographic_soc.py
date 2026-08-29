"""Phase 125: Holographic SOC endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import holographic_soc_service

router = APIRouter(prefix="/holographic-soc", tags=["Holographic SOC P125"])

class DispIn(BaseModel):
    display_name: str
    display_type: str = "volumetric"

class HoloIn(BaseModel):
    display_id: int
    hologram_type: str = "threat_globe"

@router.get("/displays")
def list_displays(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        disps = holographic_soc_service.list_displays(db, current_user.org_id)
        return [holographic_soc_service.serialize_display(d) for d in disps]
    except Exception:
        return []

@router.post("/displays")
def create_display(payload: DispIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        d = holographic_soc_service.create_display(db, current_user.org_id, payload.display_name, payload.display_type)
        return holographic_soc_service.serialize_display(d)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/holograms")
def create_holo(payload: HoloIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        h = holographic_soc_service.create_hologram(db, current_user.org_id, payload.display_id, payload.hologram_type)
        return holographic_soc_service.serialize_hologram(h)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
