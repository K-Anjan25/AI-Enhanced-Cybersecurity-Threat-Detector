"""Phase 126: Autonomous Workforce service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.autonomous_workforce import AIWorkforce, SkillMatrix, WorkforceTask

def _now():
    return datetime.now(timezone.utc)

def create_workforce(db: Session, org_id: int, name: str) -> AIWorkforce:
    wf = AIWorkforce(org_id=org_id, name=name, workforce_type="soc", total_agents=25, human_count=5, ai_count=20, autonomy_ratio=0.8, status="active")
    db.add(wf)
    db.commit()
    db.refresh(wf)
    # Skill matrix
    skills = ["threat_hunting","forensics","malware_analysis","incident_response","compliance"]
    for skill in skills:
        sm = SkillMatrix(workforce_id=wf.id, org_id=org_id, skill_name=skill, human_proficiency=75.0, ai_proficiency=85.0, gap=10.0, training_needed=False)
        db.add(sm)
    db.commit()
    return wf

def list_workforces(db: Session, org_id: int) -> List[AIWorkforce]:
    return db.query(AIWorkforce).filter(AIWorkforce.org_id == org_id).all()

def assign_task(db: Session, org_id: int, workforce_id: int, task_name: str, assign_to: str = "hunter-agent") -> WorkforceTask:
    wf = db.query(AIWorkforce).filter(AIWorkforce.id == workforce_id, AIWorkforce.org_id == org_id).first()
    if not wf:
        raise ValueError("Workforce not found")
    task = WorkforceTask(workforce_id=workforce_id, org_id=org_id, task_name=task_name, assigned_to=assign_to, assignment_type="ai" if "agent" in assign_to else "human", priority="high", status="assigned")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def serialize_workforce(w: AIWorkforce) -> Dict[str, Any]:
    return {"id": w.id, "name": w.name, "workforce_type": w.workforce_type, "total_agents": w.total_agents, "human_count": w.human_count, "ai_count": w.ai_count, "autonomy_ratio": w.autonomy_ratio, "status": w.status}
