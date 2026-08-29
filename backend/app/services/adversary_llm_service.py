"""Phase 118: Adversary LLM service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.adversary_llm import AdversaryAgent, AttackPlan, AdversaryExecution

def _now():
    return datetime.now(timezone.utc)

def create_adversary(db: Session, org_id: int, name: str, adv_type: str = "apt") -> AdversaryAgent:
    agent = AdversaryAgent(org_id=org_id, name=name, adversary_type=adv_type, llm_model="claude-3-5-sonnet", personality_json={"aggressiveness": 0.7, "stealth": 0.9, "sophistication": 0.85}, status="idle")
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

def list_adversaries(db: Session, org_id: int) -> List[AdversaryAgent]:
    return db.query(AdversaryAgent).filter(AdversaryAgent.org_id == org_id).all()

def create_attack_plan(db: Session, org_id: int, adversary_id: int, name: str, objective: str) -> AttackPlan:
    adv = db.query(AdversaryAgent).filter(AdversaryAgent.id == adversary_id, AdversaryAgent.org_id == org_id).first()
    if not adv:
        raise ValueError("Adversary not found")
    plan = AttackPlan(adversary_id=adversary_id, org_id=org_id, name=name, objective=objective, kill_chain_json=[{"phase": "initial_access", "ttp": "T1078", "technique": "Valid Accounts"}, {"phase": "persistence", "ttp": "T1053", "technique": "Scheduled Task"}, {"phase": "lateral_movement", "ttp": "T1021", "technique": "Remote Services"}, {"phase": "exfiltration", "ttp": "T1041", "technique": "Exfil Over C2"}], estimated_success=0.65, status="ready")
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

def execute_plan(db: Session, org_id: int, plan_id: int) -> List[AdversaryExecution]:
    plan = db.query(AttackPlan).filter(AttackPlan.id == plan_id, AttackPlan.org_id == org_id).first()
    if not plan:
        raise ValueError("Plan not found")
    executions = []
    for idx, step in enumerate(plan.kill_chain_json):
        exec_obj = AdversaryExecution(plan_id=plan_id, org_id=org_id, step_number=idx+1, ttp_id=step.get("ttp"), action_json=step, result_json={"success": True, "artifacts": ["log"]}, detected=(idx>=2), detection_time_seconds=120.0 if idx>=2 else None, status="completed")
        db.add(exec_obj)
        executions.append(exec_obj)
    plan.status = "completed"
    db.commit()
    for e in executions:
        db.refresh(e)
    return executions

def serialize_adversary(a: AdversaryAgent) -> Dict[str, Any]:
    return {"id": a.id, "name": a.name, "adversary_type": a.adversary_type, "llm_model": a.llm_model, "personality": a.personality_json, "status": a.status}

def serialize_plan(p: AttackPlan) -> Dict[str, Any]:
    return {"id": p.id, "adversary_id": p.adversary_id, "name": p.name, "objective": p.objective, "kill_chain": p.kill_chain_json, "estimated_success": p.estimated_success, "status": p.status}
