"""Phase 134: Neuro-Symbolic Reasoning - neural + symbolic."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class NeuroSymbolicEngine(Base):
    __tablename__ = "neuro_symbolic_engines"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    neural_model = Column(String(100), default="transformer")
    symbolic_engine = Column(String(100), default="prolog+opa")
    reasoning_mode = Column(String(50), default="hybrid")  # neural, symbolic, hybrid, iterative
    accuracy = Column(Float, default=0.93)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class SymbolicRule(Base):
    __tablename__ = "symbolic_rules"
    id = Column(Integer, primary_key=True, index=True)
    engine_id = Column(Integer, ForeignKey("neuro_symbolic_engines.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    rule_name = Column(String(300), nullable=False)
    logic_form = Column(Text, nullable=True)  # first-order logic
    natural_language = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class ReasoningTrace(Base):
    __tablename__ = "reasoning_traces"
    id = Column(Integer, primary_key=True, index=True)
    engine_id = Column(Integer, ForeignKey("neuro_symbolic_engines.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    query = Column(Text, nullable=False)
    neural_thought = Column(JSON, default=dict)
    symbolic_proof = Column(JSON, default=dict)
    final_answer = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
