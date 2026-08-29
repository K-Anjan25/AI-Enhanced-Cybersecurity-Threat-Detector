"""Phase 142: Reality Fabric endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import reality_fabric_service

router = APIRouter(prefix="/reality-fabric", tags=["Reality Fabric P142"])

class In(BaseModel):
    name: str

class AnomalyIn(BaseModel):
    fabric_id: int
    anomaly_type: str = "constant_drift"

@router.get("/fabrics")
def list_fab(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        fabs = reality_fabric_service.list_fabrics(db, current_user.org_id)
        return [reality_fabric_service.serialize_fabric(f) for f in fabs]
    except Exception:
        return []

@router.post("/fabrics")
def create_fab(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        f = reality_fabric_service.create_fabric(db, current_user.org_id, payload.name)
        return reality_fabric_service.serialize_fabric(f)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/anomalies")
def detect(payload: AnomalyIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        an = reality_fabric_service.detect_anomaly(db, current_user.org_id, payload.fabric_id, payload.anomaly_type)
        return reality_fabric_service.serialize_anomaly(an)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
