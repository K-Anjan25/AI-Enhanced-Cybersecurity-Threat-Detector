"""Phase 113: Actor DNA service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
import hashlib
from sqlalchemy.orm import Session
from app.models.actor_dna import ActorDNA, TTPPattern, ActorAttribution

def _now():
    return datetime.now(timezone.utc)

def create_actor_dna(db: Session, org_id: int, actor_name: str, genome: Dict[str, Any] = None) -> ActorDNA:
    genome = genome or {"initial_access": ["T1078","T1190"], "persistence": ["T1053"], "lateral": ["T1021"]}
    dna_str = str(genome)
    dna_hash = hashlib.sha256(dna_str.encode()).hexdigest()[:16]
    actor = ActorDNA(org_id=org_id, actor_name=actor_name, dna_hash=dna_hash, behavior_genome_json=genome, sophistication_score=85.0, first_seen=_now(), last_seen=_now())
    db.add(actor)
    db.commit()
    db.refresh(actor)
    # Seed TTP patterns
    for idx, ttp in enumerate(["T1078","T1053","T1021","T1003"]):
        pat = TTPPattern(actor_dna_id=actor.id, org_id=org_id, ttp_id=ttp, frequency=0.8 - idx*0.1, sequence_position=idx, context_json={"observed_in": "case"})
        db.add(pat)
    db.commit()
    return actor

def list_actors(db: Session, org_id: int) -> List[ActorDNA]:
    return db.query(ActorDNA).filter(ActorDNA.org_id == org_id).order_by(ActorDNA.last_seen.desc()).all()

def attribute_case(db: Session, org_id: int, case_id: int, actor_dna_id: int) -> ActorAttribution:
    attr = ActorAttribution(org_id=org_id, case_id=case_id, actor_dna_id=actor_dna_id, confidence=0.82, evidence_json={"ttp_match": 0.85, "infra_match": 0.78}, status="suspected")
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr

def serialize_actor(a: ActorDNA) -> Dict[str, Any]:
    return {"id": a.id, "actor_name": a.actor_name, "dna_hash": a.dna_hash, "behavior_genome": a.behavior_genome_json, "sophistication_score": a.sophistication_score, "first_seen": a.first_seen.isoformat() if a.first_seen else None, "last_seen": a.last_seen.isoformat() if a.last_seen else None}
