"""Phase 98: CNAPP endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import cnapp_service

router = APIRouter(prefix="/cnapp", tags=["CNAPP (Phase 98)"])

class ClusterIn(BaseModel):
    name: str
    cluster_type: str = "kubernetes"
    provider: str = "aws"
    region: str = "us-east-1"

@router.get("/clusters")
def list_clusters(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cnapp_service.seed_clusters(db, current_user.org_id)
        clusters = cnapp_service.list_clusters(db, current_user.org_id)
        return [cnapp_service.serialize_cluster(c) for c in clusters]
    except Exception:
        return []

@router.post("/clusters")
def create_cluster(payload: ClusterIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        c = cnapp_service.create_cluster(db, current_user.org_id, payload.name, payload.cluster_type, payload.provider, payload.region)
        return cnapp_service.serialize_cluster(c)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/workloads")
def list_workloads(cluster_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        workloads = cnapp_service.list_workloads(db, current_user.org_id, cluster_id)
        return [cnapp_service.serialize_workload(w) for w in workloads]
    except Exception:
        return []

@router.get("/summary")
def get_summary(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return cnapp_service.get_summary(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
