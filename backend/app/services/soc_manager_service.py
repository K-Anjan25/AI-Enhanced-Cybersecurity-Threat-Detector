"""Phase 96: AI SOC Manager service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.soc_manager import SOCManagerDashboard, AgentOrchestration, AgentPerformance
from app.models import Case

def _now():
    return datetime.now(timezone.utc)

def get_or_create_dashboard(db: Session, org_id: int) -> SOCManagerDashboard:
    dash = db.query(SOCManagerDashboard).filter(SOCManagerDashboard.org_id == org_id).first()
    if dash:
        return dash
    agents = [
        {"name": "hunter", "role": "threat_hunter", "status": "idle", "current_case_id": None, "metrics": {"cases_handled": 12, "accuracy": 92}},
        {"name": "enricher", "role": "intel_enricher", "status": "idle", "current_case_id": None, "metrics": {"cases_handled": 20, "accuracy": 88}},
        {"name": "responder", "role": "incident_responder", "status": "idle", "current_case_id": None, "metrics": {"cases_handled": 8, "accuracy": 90}},
        {"name": "compliance_checker", "role": "compliance", "status": "idle", "current_case_id": None, "metrics": {"cases_handled": 5, "accuracy": 95}},
        {"name": "risk_analyst", "role": "risk", "status": "idle", "current_case_id": None, "metrics": {"cases_handled": 15, "accuracy": 89}},
    ]
    dash = SOCManagerDashboard(org_id=org_id, name="SOC Manager", agents_json=agents, policy_json={"auto_assign": True, "max_cases_per_agent": 5})
    db.add(dash)
    db.commit()
    db.refresh(dash)
    return dash

def orchestrate_case(db: Session, org_id: int, case_id: int) -> AgentOrchestration:
    case = db.query(Case).filter(Case.id == case_id, Case.org_id == org_id).first()
    if not case:
        raise ValueError("Case not found")

    workflow = [
        {"agent": "hunter", "task": "hunt related alerts", "status": "pending", "order": 1},
        {"agent": "enricher", "task": "enrich IOCs", "status": "pending", "order": 2},
        {"agent": "risk_analyst", "task": "calculate risk", "status": "pending", "order": 3},
        {"agent": "responder", "task": "propose action", "status": "pending", "order": 4},
        {"agent": "compliance_checker", "task": "check compliance", "status": "pending", "order": 5},
    ]

    orch = AgentOrchestration(org_id=org_id, case_id=case_id, workflow_json=workflow, status="running")
    db.add(orch)
    db.commit()
    db.refresh(orch)

    # Simulate execution
    for step in workflow:
        step["status"] = "completed"
    orch.workflow_json = workflow
    orch.status = "completed"
    orch.result_json = {"consensus": "escalate", "final_action": case.proposed_action, "agents_involved": [s["agent"] for s in workflow]}
    orch.completed_at = _now()
    db.commit()
    db.refresh(orch)

    # Update dashboard agent status
    dash = get_or_create_dashboard(db, org_id)
    agents = dash.agents_json or []
    for agent in agents:
        if agent["name"] in [s["agent"] for s in workflow]:
            agent["status"] = "idle"
            agent["current_case_id"] = None
    dash.agents_json = agents
    db.commit()

    return orch

def list_orchestrations(db: Session, org_id: int) -> List[AgentOrchestration]:
    return db.query(AgentOrchestration).filter(AgentOrchestration.org_id == org_id).order_by(AgentOrchestration.created_at.desc()).limit(50).all()

def get_performance(db: Session, org_id: int) -> List[AgentPerformance]:
    return db.query(AgentPerformance).filter(AgentPerformance.org_id == org_id).order_by(AgentPerformance.recorded_at.desc()).limit(50).all()

def serialize_dashboard(d: SOCManagerDashboard) -> Dict[str, Any]:
    return {"id": d.id, "name": d.name, "agents": d.agents_json, "policy": d.policy_json, "created_at": d.created_at.isoformat() if d.created_at else None}

def serialize_orchestration(o: AgentOrchestration) -> Dict[str, Any]:
    return {"id": o.id, "case_id": o.case_id, "workflow": o.workflow_json, "status": o.status, "result": o.result_json, "created_at": o.created_at.isoformat() if o.created_at else None, "completed_at": o.completed_at.isoformat() if o.completed_at else None}
