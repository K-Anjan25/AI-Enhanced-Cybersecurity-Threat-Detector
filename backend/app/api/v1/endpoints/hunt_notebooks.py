"""Phase 86: Hunt Notebooks endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import hunt_notebook_service

router = APIRouter(prefix="/hunt-notebooks", tags=["Hunt Notebooks (Phase 86)"])

class NotebookIn(BaseModel):
    name: str
    description: Optional[str] = None
    kernel: str = "python"
    tags: Optional[List[str]] = None

class CellIn(BaseModel):
    cell_type: str = "code"
    source: str
    position: Optional[int] = None

@router.get("/")
def list_notebooks(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        hunt_notebook_service.seed_notebooks(db, current_user.org_id)
        nbs = hunt_notebook_service.list_notebooks(db, current_user.org_id)
        return [hunt_notebook_service.serialize_notebook(n) for n in nbs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/")
def create_notebook(payload: NotebookIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        nb = hunt_notebook_service.create_notebook(db, current_user.org_id, payload.name, payload.description, payload.kernel, payload.tags, created_by_user_id=current_user.id)
        return hunt_notebook_service.serialize_notebook(nb)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/{notebook_id}/cells")
def list_cells(notebook_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cells = hunt_notebook_service.list_cells(db, current_user.org_id, notebook_id)
        return [hunt_notebook_service.serialize_cell(c) for c in cells]
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{notebook_id}/cells")
def add_cell(notebook_id: int, payload: CellIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cell = hunt_notebook_service.add_cell(db, current_user.org_id, notebook_id, payload.cell_type, payload.source, payload.position)
        return hunt_notebook_service.serialize_cell(cell)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/cells/{cell_id}/execute")
def execute_cell(cell_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cell = hunt_notebook_service.execute_cell(db, current_user.org_id, cell_id)
        return hunt_notebook_service.serialize_cell(cell)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{notebook_id}/execute")
def execute_notebook(notebook_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exec_log = hunt_notebook_service.execute_notebook(db, current_user.org_id, notebook_id, executed_by_user_id=current_user.id)
        return {"id": exec_log.id, "status": exec_log.status, "results": exec_log.results_json, "started_at": exec_log.started_at.isoformat() if exec_log.started_at else None, "completed_at": exec_log.completed_at.isoformat() if exec_log.completed_at else None}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
