"""Phase 85: SOAR Approval Workflows service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.approval_workflow import ApprovalWorkflow, ApprovalInstance, ApprovalTask
from app.models.soar import SoarAction


def _now():
    return datetime.now(timezone.utc)


def create_workflow(db: Session, org_id: int, name: str, description: str = None, steps: List[Dict] = None, trigger: Dict = None, created_by_user_id: int = None) -> ApprovalWorkflow:
    wf = ApprovalWorkflow(org_id=org_id, name=name, description=description, steps_json=steps or [], trigger_json=trigger or {}, created_by_user_id=created_by_user_id)
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


def list_workflows(db: Session, org_id: int) -> List[ApprovalWorkflow]:
    return db.query(ApprovalWorkflow).filter(ApprovalWorkflow.org_id == org_id, ApprovalWorkflow.is_active == True).order_by(ApprovalWorkflow.created_at.desc()).all()


def seed_workflows(db: Session, org_id: int) -> List[ApprovalWorkflow]:
    existing = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.org_id == org_id).count()
    if existing > 0:
        return list_workflows(db, org_id)
    defaults = [
        {"name": "Critical Action - SOC Lead Approval", "description": "Requires SOC Lead for HIGH/CRITICAL block/isolate", "steps": [{"step": 1, "name": "SOC Lead", "approver_roles": ["admin"], "action_types": ["block_ip", "isolate_host"], "min_approvals": 1}], "trigger": {"severity": ["HIGH", "CRITICAL"], "action_types": ["block_ip", "isolate_host"]}},
        {"name": "Compliance Sensitive - Dual Approval", "description": "Requires 2 approvals for compliance-related actions", "steps": [{"step": 1, "name": "Analyst", "approver_roles": ["analyst", "admin"], "min_approvals": 1}, {"step": 2, "name": "Admin", "approver_roles": ["admin"], "min_approvals": 1}], "trigger": {"action_types": ["quarantine_email", "disable_user"]}},
    ]
    created = []
    for d in defaults:
        wf = create_workflow(db, org_id, d["name"], d["description"], d["steps"], d["trigger"])
        created.append(wf)
    return created


def request_approval(db: Session, org_id: int, workflow_id: int, action_type: str, target: str, soar_action_id: int = None, case_id: int = None, requested_by_user_id: int = None) -> ApprovalInstance:
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id, ApprovalWorkflow.org_id == org_id).first()
    if not wf:
        raise ValueError("Workflow not found")

    instance = ApprovalInstance(org_id=org_id, workflow_id=workflow_id, soar_action_id=soar_action_id, case_id=case_id, action_type=action_type, target=target, requested_by_user_id=requested_by_user_id, current_step=1, status="pending", approvals_json=[])
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # Create tasks for first step
    steps = wf.steps_json or []
    if steps:
        first = steps[0]
        roles = first.get("approver_roles", ["admin"])
        for role in roles:
            task = ApprovalTask(org_id=org_id, instance_id=instance.id, step=1, assignee_role=role, status="pending")
            db.add(task)
        db.commit()

    return instance


def list_instances(db: Session, org_id: int, status: str = None) -> List[ApprovalInstance]:
    q = db.query(ApprovalInstance).filter(ApprovalInstance.org_id == org_id)
    if status:
        q = q.filter(ApprovalInstance.status == status)
    return q.order_by(ApprovalInstance.created_at.desc()).limit(100).all()


def approve_instance(db: Session, org_id: int, instance_id: int, approver_user_id: int, decision: str = "approved", comment: str = None) -> ApprovalInstance:
    inst = db.query(ApprovalInstance).filter(ApprovalInstance.id == instance_id, ApprovalInstance.org_id == org_id).first()
    if not inst:
        raise ValueError("Instance not found")
    if inst.status != "pending":
        return inst

    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == inst.workflow_id).first()
    steps = wf.steps_json or []
    current_step_def = next((s for s in steps if s.get("step") == inst.current_step), None)
    if not current_step_def:
        inst.status = "approved"
        inst.decided_at = _now()
        db.commit()
        return inst

    # Record approval
    approvals = inst.approvals_json or []
    approvals.append({"user_id": approver_user_id, "decision": decision, "comment": comment, "step": inst.current_step, "at": _now().isoformat()})
    inst.approvals_json = approvals

    # Update task
    task = db.query(ApprovalTask).filter(ApprovalTask.instance_id == instance_id, ApprovalTask.step == inst.current_step, ApprovalTask.status == "pending").first()
    if task:
        task.status = decision
        task.comment = comment
        task.decided_at = _now()
        task.assignee_user_id = approver_user_id

    if decision == "rejected":
        inst.status = "rejected"
        inst.decided_at = _now()
        db.commit()
        db.refresh(inst)
        return inst

    # Check if step complete (min_approvals)
    min_approvals = current_step_def.get("min_approvals", 1)
    step_approvals = [a for a in approvals if a.get("step") == inst.current_step and a.get("decision") == "approved"]
    if len(step_approvals) >= min_approvals:
        # Move to next step or complete
        next_step = inst.current_step + 1
        next_def = next((s for s in steps if s.get("step") == next_step), None)
        if next_def:
            inst.current_step = next_step
            # Create tasks for next step
            for role in next_def.get("approver_roles", ["admin"]):
                t = ApprovalTask(org_id=org_id, instance_id=inst.id, step=next_step, assignee_role=role, status="pending")
                db.add(t)
        else:
            inst.status = "approved"
            inst.decided_at = _now()
            # If linked SOAR action, approve it
            if inst.soar_action_id:
                action = db.query(SoarAction).filter(SoarAction.id == inst.soar_action_id).first()
                if action:
                    action.status = "approved"

    db.commit()
    db.refresh(inst)
    return inst


def serialize_workflow(w: ApprovalWorkflow) -> Dict[str, Any]:
    return {"id": w.id, "name": w.name, "description": w.description, "steps": w.steps_json, "trigger": w.trigger_json, "is_active": w.is_active, "created_at": w.created_at.isoformat() if w.created_at else None}


def serialize_instance(i: ApprovalInstance) -> Dict[str, Any]:
    return {"id": i.id, "workflow_id": i.workflow_id, "action_type": i.action_type, "target": i.target, "case_id": i.case_id, "current_step": i.current_step, "status": i.status, "approvals": i.approvals_json, "created_at": i.created_at.isoformat() if i.created_at else None, "decided_at": i.decided_at.isoformat() if i.decided_at else None}
