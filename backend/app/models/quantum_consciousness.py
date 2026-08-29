"""Phase 132: Quantum Consciousness - entanglement, superposition."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class QuantumConsciousnessNode(Base):
    __tablename__ = "quantum_consciousness_nodes"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_name = Column(String(300), nullable=False)
    qubit_count = Column(Integer, default=100)
    entanglement_degree = Column(Float, default=0.95)
    coherence_time_ms = Column(Float, default=100.0)
    consciousness_state = Column(String(50), default="superposition")  # superposition, entangled, collapsed, transcendent
    status = Column(String(20), default="entangled")
    created_at = Column(DateTime(timezone=True), default=_now)

class EntanglementLink(Base):
    __tablename__ = "entanglement_links"
    id = Column(Integer, primary_key=True, index=True)
    source_node_id = Column(Integer, ForeignKey("quantum_consciousness_nodes.id"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("quantum_consciousness_nodes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    entanglement_strength = Column(Float, default=0.9)
    fidelity = Column(Float, default=0.98)
    bell_state = Column(String(20), default="Phi+")
    created_at = Column(DateTime(timezone=True), default=_now)

class QuantumThought(Base):
    __tablename__ = "quantum_thoughts"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("quantum_consciousness_nodes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    thought = Column(Text, nullable=False)
    superposition_json = Column(JSON, default=list)  # multiple simultaneous thoughts
    collapsed_decision = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
