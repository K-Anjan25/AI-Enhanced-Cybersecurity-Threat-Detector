"""Phase 78-79: Purple team service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.purple_team import PurpleTeamExercise, PurpleTeamFinding
from app.models import SecurityAlert, Case


def _now():
    return datetime.now(timezone.utc)


def create_exercise(db: Session, org_id: int, name: str, description: str = None, mitre_tactic: str = None, mitre_technique_id: str = None, exercise_type: str = "atomic", steps: List[Dict] = None, created_by_user_id: int = None) -> PurpleTeamExercise:
    ex = PurpleTeamExercise(org_id=org_id, name=name, description=description, mitre_tactic=mitre_tactic, mitre_technique_id=mitre_technique_id, exercise_type=exercise_type, steps_json=steps or [], status="planned", created_by_user_id=created_by_user_id)
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


def list_exercises(db: Session, org_id: int) -> List[PurpleTeamExercise]:
    return db.query(PurpleTeamExercise).filter(PurpleTeamExercise.org_id == org_id).order_by(PurpleTeamExercise.created_at.desc()).all()


def run_exercise(db: Session, org_id: int, exercise_id: int) -> PurpleTeamExercise:
    """Run exercise: simulate attack steps, create alerts, measure detection."""
    ex = db.query(PurpleTeamExercise).filter(PurpleTeamExercise.id == exercise_id, PurpleTeamExercise.org_id == org_id).first()
    if not ex:
        raise ValueError("Exercise not found")
    ex.status = "running"
    ex.started_at = _now()
    db.commit()

    # Simulate: create a mock alert for each step
    alerts_created = []
    detected = False
    for step in ex.steps_json or []:
        # Create alert
        alert = SecurityAlert(org_id=org_id, severity="HIGH", source="purple_team", message=f"Purple team exercise {ex.name} step {step.get('action')} {step.get('command')}", alert_type="purple_team", mitre_tactic=ex.mitre_tactic, mitre_technique_id=ex.mitre_technique_id)
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alerts_created.append(alert.id)
        detected = True  # Simulate detection

    ex.status = "completed"
    ex.completed_at = _now()
    ex.results_json = {"detected": detected, "alerts_created": alerts_created, "time_to_detect_seconds": 120, "steps_executed": len(ex.steps_json or [])}
    ex.score = 85 if detected else 20
    db.commit()
    db.refresh(ex)

    # Create findings if not detected well
    if not detected or ex.score < 70:
        finding = PurpleTeamFinding(org_id=org_id, exercise_id=ex.id, title=f"Detection gap for {ex.mitre_technique_id}", finding_type="detection_gap", severity="MEDIUM", description=f"Exercise {ex.name} technique {ex.mitre_technique_id} not detected with high confidence", recommendation="Create detection rule for this technique")
        db.add(finding)
        db.commit()

    return ex


def list_findings(db: Session, org_id: int, exercise_id: int = None) -> List[PurpleTeamFinding]:
    q = db.query(PurpleTeamFinding).filter(PurpleTeamFinding.org_id == org_id)
    if exercise_id:
        q = q.filter(PurpleTeamFinding.exercise_id == exercise_id)
    return q.order_by(PurpleTeamFinding.created_at.desc()).all()


def seed_exercises(db: Session, org_id: int) -> List[PurpleTeamExercise]:
    existing = db.query(PurpleTeamExercise).filter(PurpleTeamExercise.org_id == org_id).count()
    if existing > 0:
        return list_exercises(db, org_id)
    defaults = [
        {"name": "T1059 - PowerShell Execution", "description": "Simulate PowerShell download cradle", "mitre_tactic": "execution", "mitre_technique_id": "T1059.001", "exercise_type": "atomic", "steps": [{"action": "execute", "command": "powershell -enc ...", "expected_detection": "EDR alert"}]},
        {"name": "T1078 - Valid Accounts", "description": "Simulate login with valid creds", "mitre_tactic": "persistence", "mitre_technique_id": "T1078", "exercise_type": "atomic", "steps": [{"action": "login", "command": "ssh valid_user@target", "expected_detection": "Impossible travel"}]},
        {"name": "T1053 - Scheduled Task", "description": "Create scheduled task for persistence", "mitre_tactic": "persistence", "mitre_technique_id": "T1053.005", "exercise_type": "chain", "steps": [{"action": "create_task", "command": "schtasks /create ..."}, {"action": "execute", "command": "task runs payload"}]},
    ]
    created = []
    for d in defaults:
        ex = create_exercise(db, org_id=org_id, name=d["name"], description=d["description"], mitre_tactic=d["mitre_tactic"], mitre_technique_id=d["mitre_technique_id"], exercise_type=d["exercise_type"], steps=d["steps"])
        created.append(ex)
    return created


def serialize_exercise(e: PurpleTeamExercise) -> Dict[str, Any]:
    return {"id": e.id, "name": e.name, "description": e.description, "mitre_tactic": e.mitre_tactic, "mitre_technique_id": e.mitre_technique_id, "exercise_type": e.exercise_type, "status": e.status, "score": e.score, "results": e.results_json, "created_at": e.created_at.isoformat() if e.created_at else None, "started_at": e.started_at.isoformat() if e.started_at else None, "completed_at": e.completed_at.isoformat() if e.completed_at else None}


def serialize_finding(f: PurpleTeamFinding) -> Dict[str, Any]:
    return {"id": f.id, "exercise_id": f.exercise_id, "title": f.title, "finding_type": f.finding_type, "severity": f.severity, "description": f.description, "recommendation": f.recommendation, "status": f.status, "created_at": f.created_at.isoformat() if f.created_at else None}
