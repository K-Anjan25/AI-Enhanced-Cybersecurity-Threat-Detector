"""Phase 132: Quantum Consciousness endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import quantum_consciousness_service

router = APIRouter(prefix="/quantum-consciousness", tags=["Quantum Consciousness P132"])

class NodeIn(BaseModel):
    node_name: str
    qubit_count: int = 100

class EntangleIn(BaseModel):
    source_id: int
    target_id: int

class ThoughtIn(BaseModel):
    node_id: int
    thought: str = "If breach in 80% universes, then imminent in primary"

@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        nodes = quantum_consciousness_service.list_nodes(db, current_user.org_id)
        return [quantum_consciousness_service.serialize_node(n) for n in nodes]
    except Exception:
        return []

@router.post("/nodes")
def create_node(payload: NodeIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        n = quantum_consciousness_service.create_node(db, current_user.org_id, payload.node_name, payload.qubit_count)
        return quantum_consciousness_service.serialize_node(n)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/entangle")
def entangle(payload: EntangleIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        link = quantum_consciousness_service.entangle_nodes(db, current_user.org_id, payload.source_id, payload.target_id)
        return {"id": link.id, "entanglement_strength": link.entanglement_strength, "fidelity": link.fidelity, "bell_state": link.bell_state}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/thoughts")
def thought(payload: ThoughtIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = quantum_consciousness_service.create_thought(db, current_user.org_id, payload.node_id, payload.thought)
        return {"id": t.id, "thought": t.thought, "superposition": t.superposition_json, "collapsed": t.collapsed_decision, "confidence": t.confidence}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
