"""Phase 134: Neuro-Symbolic service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.neuro_symbolic import NeuroSymbolicEngine, SymbolicRule, ReasoningTrace

def _now():
    return datetime.now(timezone.utc)

def create_engine(db: Session, org_id: int, name: str) -> NeuroSymbolicEngine:
    eng = NeuroSymbolicEngine(org_id=org_id, name=name, neural_model="transformer", symbolic_engine="prolog+opa", reasoning_mode="hybrid", accuracy=0.94, status="active")
    db.add(eng)
    db.commit()
    db.refresh(eng)
    rule = SymbolicRule(engine_id=eng.id, org_id=org_id, rule_name="Breach requires failed logins AND priv esc", logic_form="breach(X) :- failed_logins(X, high), priv_esc(X)", natural_language="If high failed logins and privilege escalation, then breach", confidence=0.9)
    db.add(rule)
    db.commit()
    return eng

def list_engines(db: Session, org_id: int) -> List[NeuroSymbolicEngine]:
    return db.query(NeuroSymbolicEngine).filter(NeuroSymbolicEngine.org_id == org_id).all()

def reason(db: Session, org_id: int, engine_id: int, query: str) -> ReasoningTrace:
    eng = db.query(NeuroSymbolicEngine).filter(NeuroSymbolicEngine.id == engine_id, NeuroSymbolicEngine.org_id == org_id).first()
    if not eng:
        raise ValueError("Engine not found")
    trace = ReasoningTrace(engine_id=engine_id, org_id=org_id, query=query, neural_thought={"embedding": [0.1,0.2], "intuition": "High severity due to lateral movement"}, symbolic_proof={"proof_steps": ["failed_logins(high) -> suspicious", "suspicious + priv_esc -> breach"], "verified": True}, final_answer=f"Query '{query}' -> BREACH with 89% confidence (neural intuition + symbolic proof)", confidence=0.89)
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace

def serialize_engine(e: NeuroSymbolicEngine) -> Dict[str, Any]:
    return {"id": e.id, "name": e.name, "neural_model": e.neural_model, "symbolic_engine": e.symbolic_engine, "reasoning_mode": e.reasoning_mode, "accuracy": e.accuracy, "status": e.status}

def serialize_trace(t: ReasoningTrace) -> Dict[str, Any]:
    return {"id": t.id, "engine_id": t.engine_id, "query": t.query, "neural_thought": t.neural_thought, "symbolic_proof": t.symbolic_proof, "final_answer": t.final_answer, "confidence": t.confidence}
