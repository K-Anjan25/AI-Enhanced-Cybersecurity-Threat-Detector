"""Phase 117: Intel Mesh endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import intel_mesh_service

router = APIRouter(prefix="/intel-mesh", tags=["Intel Mesh P117"])

class NodeIn(BaseModel):
    node_name: str
    region: str = "us-east-1"

@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        nodes = intel_mesh_service.list_nodes(db, current_user.org_id)
        return [intel_mesh_service.serialize_node(n) for n in nodes]
    except Exception:
        return []

@router.post("/nodes")
def create_node(payload: NodeIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        n = intel_mesh_service.create_node(db, current_user.org_id, payload.node_name, payload.region)
        return intel_mesh_service.serialize_node(n)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/nodes/{node_id}/sync")
def sync_node(node_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sync = intel_mesh_service.sync_node(db, current_user.org_id, node_id)
        return {"id": sync.id, "records_synced": sync.records_synced, "latency_ms": sync.latency_ms, "status": sync.sync_status}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/intel")
def list_intel(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        intel = intel_mesh_service.list_intel(db, current_user.org_id)
        return [intel_mesh_service.serialize_intel(i) for i in intel]
    except Exception:
        return []
