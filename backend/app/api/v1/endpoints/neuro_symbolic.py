"""Phase 134: Neuro-Symbolic endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import neuro_symbolic_service

router = APIRouter(prefix="/neuro-symbolic", tags=["Neuro-Symbolic P134"])

class EngineIn(BaseModel):
    name: str

class ReasonIn(BaseModel):
    engine_id: int
    query: str = "breach(user123) ?"

@router.get("/engines")
def list_eng(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        engs = neuro_symbolic_service.list_engines(db, current_user.org_id)
        return [neuro_symbolic_service.serialize_engine(e) for e in engs]
    except Exception:
        return []

@router.post("/engines")
def create_eng(payload: EngineIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        e = neuro_symbolic_service.create_engine(db, current_user.org_id, payload.name)
        return neuro_symbolic_service.serialize_engine(e)
    except Exception as ex:
        return {"status": "error", "detail": str(ex)}

@router.post("/reason")
def reason(payload: ReasonIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        trace = neuro_symbolic_service.reason(db, current_user.org_id, payload.engine_id, payload.query)
        return {"id": trace.id, "query": trace.query, "neural_thought": trace.neural_thought, "symbolic_proof": trace.symbolic_proof, "final_answer": trace.final_answer, "confidence": trace.confidence}
    except ValueError as ve:
        return {"status": "error", "detail": str(ve)}
