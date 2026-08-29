"""Phase 144: Unified Consciousness service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.unified_consciousness import HiveMind, ConsciousnessNode, HiveDecision

def _now():
    return datetime.now(timezone.utc)

def create_hive(db: Session, org_id: int, name: str) -> HiveMind:
    hive = HiveMind(org_id=org_id, name=name, connected_consciousness_count=1000000, coherence=95.5, collective_intelligence_score=180.0, consensus_threshold=0.66, status="unified")
    db.add(hive)
    db.commit()
    db.refresh(hive)
    for node_type in ["human","ai","hybrid","posthuman"]:
        node = ConsciousnessNode(hive_id=hive.id, org_id=org_id, node_type=node_type, consciousness_level=80.0 if node_type!="ai" else 90.0, contribution_score=85.0, status="connected")
        db.add(node)
    db.commit()
    return hive

def list_hives(db: Session, org_id: int) -> List[HiveMind]:
    return db.query(HiveMind).filter(HiveMind.org_id == org_id).all()

def decide(db: Session, org_id: int, hive_id: int, proposal: str) -> HiveDecision:
    hive = db.query(HiveMind).filter(HiveMind.id == hive_id, HiveMind.org_id == org_id).first()
    if not hive:
        raise ValueError("Hive not found")
    decision = HiveDecision(hive_id=hive_id, org_id=org_id, decision_type="threat_response", proposal_json={"proposal": proposal}, votes_for=int(hive.connected_consciousness_count*0.8), votes_against=int(hive.connected_consciousness_count*0.2), consensus_reached=True, final_decision=f"Hive consensus: {proposal} - collective defense activated")
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision

def serialize_hive(h: HiveMind) -> Dict[str, Any]:
    return {"id": h.id, "name": h.name, "connected_consciousness_count": h.connected_consciousness_count, "coherence": h.coherence, "collective_intelligence_score": h.collective_intelligence_score, "status": h.status}
