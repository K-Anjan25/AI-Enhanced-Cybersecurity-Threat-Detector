"""Phase 107: Supply Chain v2 endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import supply_chain_v2_service

router = APIRouter(prefix="/supply-chain-v2", tags=["Supply Chain v2 P107"])

class GraphIn(BaseModel):
    name: str
    root_component: str = "noctra-api"

class VendorIn(BaseModel):
    vendor_name: str

@router.get("/graphs")
def list_graphs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        graphs = supply_chain_v2_service.list_graphs(db, current_user.org_id)
        return [supply_chain_v2_service.serialize_graph(g) for g in graphs]
    except Exception:
        return []

@router.post("/graphs")
def create_graph(payload: GraphIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        g = supply_chain_v2_service.create_graph(db, current_user.org_id, payload.name, payload.root_component)
        return supply_chain_v2_service.serialize_graph(g)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/vendor-assess")
def assess_vendor(payload: VendorIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        v = supply_chain_v2_service.assess_vendor(db, current_user.org_id, payload.vendor_name)
        return supply_chain_v2_service.serialize_vendor(v)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/vendors")
def list_vendors(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        vendors = supply_chain_v2_service.list_vendors(db, current_user.org_id)
        return [supply_chain_v2_service.serialize_vendor(v) for v in vendors]
    except Exception:
        return []
