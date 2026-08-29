"""Phase 94: CART service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.cart import CART_Job, CART_Execution, CART_Finding

def _now():
    return datetime.now(timezone.utc)

def create_job(db: Session, org_id: int, name: str, description: str = None, schedule_cron: str = "0 2 * * *", config: Dict = None) -> CART_Job:
    job = CART_Job(org_id=org_id, name=name, description=description, schedule_cron=schedule_cron, config_json=config or {"techniques": ["T1059", "T1078"], "intensity": "low"}, is_scheduled=True, status="scheduled")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def list_jobs(db: Session, org_id: int) -> List[CART_Job]:
    return db.query(CART_Job).filter(CART_Job.org_id == org_id).order_by(CART_Job.created_at.desc()).all()

def run_job(db: Session, org_id: int, job_id: int) -> CART_Execution:
    job = db.query(CART_Job).filter(CART_Job.id == job_id, CART_Job.org_id == org_id).first()
    if not job:
        raise ValueError("Job not found")
    job.status = "running"
    job.last_run_at = _now()
    db.commit()

    execution = CART_Execution(org_id=org_id, job_id=job_id, status="running", total_steps=len(job.config_json.get("techniques", []))*2)
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # Mock execution
    techniques = job.config_json.get("techniques", ["T1059", "T1078"])
    results = []
    detected = 0
    for tech in techniques:
        # Simulate detection
        is_detected = True if tech != "T1078" else False  # T1078 often missed
        results.append({"technique": tech, "detected": is_detected, "time_to_detect": 90 if is_detected else None})
        if is_detected:
            detected += 1
        else:
            finding = CART_Finding(org_id=org_id, execution_id=execution.id, title=f"Detection gap {tech}", technique_id=tech, severity="MEDIUM", description=f"Technique {tech} not detected", is_detection_gap=True)
            db.add(finding)

    execution.total_steps = len(techniques)
    execution.detected_steps = detected
    execution.detection_rate = (detected / max(1, len(techniques)) * 100)
    execution.results_json = {"steps": results, "detection_rate": execution.detection_rate}
    execution.status = "completed"
    execution.completed_at = _now()
    db.commit()
    db.refresh(execution)

    job.status = "scheduled"
    job.next_run_at = _now()
    db.commit()

    return execution

def serialize_job(j: CART_Job) -> Dict[str, Any]:
    return {"id": j.id, "name": j.name, "description": j.description, "schedule_cron": j.schedule_cron, "is_scheduled": j.is_scheduled, "config": j.config_json, "status": j.status, "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None}

def serialize_exec(e: CART_Execution) -> Dict[str, Any]:
    return {"id": e.id, "job_id": e.job_id, "status": e.status, "total_steps": e.total_steps, "detected_steps": e.detected_steps, "detection_rate": e.detection_rate, "results": e.results_json, "started_at": e.started_at.isoformat() if e.started_at else None, "completed_at": e.completed_at.isoformat() if e.completed_at else None}
