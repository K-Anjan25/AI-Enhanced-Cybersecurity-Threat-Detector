"""Phase 136: Temporal Defense endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import temporal_defense_service

router = APIRouter(prefix="/temporal-defense", tags=["Temporal Defense P136"])

class TimelineIn(BaseModel):
    name: str
    timeline_type: str = "primary"

class AnomalyIn(BaseModel):
    timeline_id: int
    anomaly_type: str = "retrocausal_attack"

@router.get("/timelines")
def list_tl(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        tls = temporal_defense_service.list_timelines(db, current_user.org_id)
        return [temporal_defense_service.serialize_timeline(t) for t in tls]
    except Exception:
        return []

@router.post("/timelines")
def create_tl(payload: TimelineIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        tl = temporal_defense_service.create_timeline(db, current_user.org_id, payload.name, payload.timeline_type)
        return temporal_defense_service.serialize_timeline(tl)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/anomalies")
def detect_anomaly(payload: AnomalyIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        an = temporal_defense_service.detect_anomaly(db, current_user.org_id, payload.timeline_id, payload.anomaly_type)
        return temporal_defense_service.serialize_anomaly(an)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
