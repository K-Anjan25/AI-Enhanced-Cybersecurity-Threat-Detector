"""Phase 132: Quantum Consciousness service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.quantum_consciousness import QuantumConsciousnessNode, EntanglementLink, QuantumThought

def _now():
    return datetime.now(timezone.utc)

def create_node(db: Session, org_id: int, name: str, qubits: int = 100) -> QuantumConsciousnessNode:
    node = QuantumConsciousnessNode(org_id=org_id, node_name=name, qubit_count=qubits, entanglement_degree=0.95, coherence_time_ms=150.0, consciousness_state="superposition", status="entangled")
    db.add(node)
    db.commit()
    db.refresh(node)
    return node

def list_nodes(db: Session, org_id: int) -> List[QuantumConsciousnessNode]:
    return db.query(QuantumConsciousnessNode).filter(QuantumConsciousnessNode.org_id == org_id).all()

def entangle_nodes(db: Session, org_id: int, source_id: int, target_id: int) -> EntanglementLink:
    src = db.query(QuantumConsciousnessNode).filter(QuantumConsciousnessNode.id == source_id, QuantumConsciousnessNode.org_id == org_id).first()
    tgt = db.query(QuantumConsciousnessNode).filter(QuantumConsciousnessNode.id == target_id, QuantumConsciousnessNode.org_id == org_id).first()
    if not src or not tgt:
        raise ValueError("Nodes not found")
    link = EntanglementLink(source_node_id=source_id, target_node_id=target_id, org_id=org_id, entanglement_strength=0.92, fidelity=0.99, bell_state="Phi+")
    db.add(link)
    db.commit()
    db.refresh(link)
    return link

def create_thought(db: Session, org_id: int, node_id: int, thought: str) -> QuantumThought:
    node = db.query(QuantumConsciousnessNode).filter(QuantumConsciousnessNode.id == node_id, QuantumConsciousnessNode.org_id == org_id).first()
    if not node:
        raise ValueError("Node not found")
    qt = QuantumThought(node_id=node_id, org_id=org_id, thought=thought, superposition_json=[{"thought": thought, "prob": 0.6}, {"thought": f"Alternative: {thought} inverted", "prob": 0.4}], collapsed_decision=thought, confidence=0.85)
    db.add(qt)
    db.commit()
    db.refresh(qt)
    return qt

def serialize_node(n: QuantumConsciousnessNode) -> Dict[str, Any]:
    return {"id": n.id, "node_name": n.node_name, "qubit_count": n.qubit_count, "entanglement_degree": n.entanglement_degree, "coherence_time_ms": n.coherence_time_ms, "consciousness_state": n.consciousness_state, "status": n.status}
