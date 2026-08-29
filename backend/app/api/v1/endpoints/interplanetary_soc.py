"""Phase 121: Interplanetary SOC endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import interplanetary_soc_service

router = APIRouter(prefix="/interplanetary-soc", tags=["Interplanetary SOC P121"])

class NodeIn(BaseModel):
    node_name: str
    node_type: str = "satellite"
    location: str = "LEO"

class TeleIn(BaseModel):
    node_id: int
    data: Dict[str, Any]

@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        nodes = interplanetary_soc_service.list_nodes(db, current_user.org_id)
        return [interplanetary_soc_service.serialize_node(n) for n in nodes]
    except Exception:
        return []

@router.post("/nodes")
def create_node(payload: NodeIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        n = interplanetary_soc_service.create_node(db, current_user.org_id, payload.node_name, payload.node_type, payload.location)
        return interplanetary_soc_service.serialize_node(n)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/telemetry")
def ingest(payload: TeleIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        tele = interplanetary_soc_service.ingest_telemetry(db, current_user.org_id, payload.node_id, payload.data)
        return {"id": tele.id, "is_anomaly": tele.is_anomaly, "signal_strength": tele.signal_strength}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
