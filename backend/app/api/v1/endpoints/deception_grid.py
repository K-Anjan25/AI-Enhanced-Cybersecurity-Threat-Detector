"""Phase 109: Deception Grid endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import deception_grid_service

router = APIRouter(prefix="/deception-grid", tags=["Deception Grid P109"])

class GridIn(BaseModel):
    name: str
    grid_type: str = "enterprise"

@router.get("/grids")
def list_grids(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        grids = deception_grid_service.list_grids(db, current_user.org_id)
        return [deception_grid_service.serialize_grid(g) for g in grids]
    except Exception:
        return []

@router.post("/grids")
def create_grid(payload: GridIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        g = deception_grid_service.create_grid(db, current_user.org_id, payload.name, payload.grid_type)
        return deception_grid_service.serialize_grid(g)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/nodes")
def list_nodes(grid_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        nodes = deception_grid_service.list_nodes(db, current_user.org_id, grid_id)
        return [deception_grid_service.serialize_node(n) for n in nodes]
    except Exception:
        return []

@router.post("/nodes/{node_id}/simulate")
def simulate(node_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        inter = deception_grid_service.simulate_interaction(db, current_user.org_id, node_id)
        return {"id": inter.id, "attacker_ip": inter.attacker_ip, "interaction_type": inter.interaction_type, "ttp": inter.ttp_observed}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
