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


_DECISIONS = ("approved", "rejected")


def approve_instance(db: Session, org_id: int, instance_id: int, approver_user_id: int, decision: str = "approved", comment: str = None) -> ApprovalInstance:
    """Record one person's decision on a pending approval.

    Three rules are enforced here rather than in the UI, because an approval
    control that can be bypassed by calling the API directly is not a control:

    * Only "approved" or "rejected". Any other string used to be written into
      the audit trail verbatim while counting as neither, leaving the request
      stuck with a meaningless decision recorded against a named user.
    * Nobody approves their own request. Otherwise the requester satisfies the
      review themselves and the second pair of eyes is imaginary.
    * Nobody decides the same request twice, at any step. Checking only the
      current step was not enough: the first approval advances the instance, so
      the same person passed the check again on step two and satisfied a
      two-stage workflow alone — exactly what dual approval exists to prevent.
    """
    if decision not in _DECISIONS:
        raise ValueError(
            f"Unknown decision {decision!r}. Expected one of: {', '.join(_DECISIONS)}."
        )

    # Row lock first: the checks below are read-then-write, and without it two
    # simultaneous approvers both read "pending" and both proceed. Postgres
    # serialises here; SQLite ignores it, so the guarded UPDATE stays too.
    inst = (
        db.query(ApprovalInstance)
        .filter(ApprovalInstance.id == instance_id, ApprovalInstance.org_id == org_id)
        .with_for_update()
        .first()
    )
    if not inst:
        raise ValueError("Instance not found")
    if inst.status != "pending":
        raise ValueError(
            f"This request is already {inst.status} and cannot be decided again."
        )

    if inst.requested_by_user_id is not None and approver_user_id == inst.requested_by_user_id:
        raise ValueError(
            "You raised this request, so you cannot approve it. Separation of "
            "duties requires a different approver."
        )

    already = [
        a for a in (inst.approvals_json or [])
        if a.get("user_id") == approver_user_id
    ]
    if already:
        raise ValueError(
            "You have already decided this request. Each stage needs a "
            "different approver."
        )

    # Everything above is a read-then-write, so two simultaneous calls can both
    # pass it. Claim the step with a conditional UPDATE: whoever changes a row
    # wins, everyone else is told the step moved on. Without this, four parallel
    # approvals all succeeded and one person could clear a dual-approval
    # workflow by firing two requests at once.
    claimed_step = inst.current_step
    claimed = (
        db.query(ApprovalInstance)
        .filter(
            ApprovalInstance.id == instance_id,
            ApprovalInstance.org_id == org_id,
            ApprovalInstance.status == "pending",
            ApprovalInstance.current_step == claimed_step,
        )
        .update(
            {ApprovalInstance.status: "deciding"},
            synchronize_session=False,
        )
    )
    db.commit()
    if not claimed:
        raise ValueError(
            "This request was decided by someone else while you were looking "
            "at it. Reload to see the current state."
        )

    # The row now reads "deciding", which is what locks other callers out.
    # Resetting it to "pending" here would release the claim before the
    # decision is recorded, letting a second approver walk straight in — that
    # is how two parallel approvals both succeeded. The status is restored
    # further down, in the same transaction that records the approval.
    db.expire(inst)


    inst.status = "pending"

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


def serialize_instance(i: ApprovalInstance, workflow: ApprovalWorkflow = None) -> Dict[str, Any]:
    """Instance for the queue.

    Carries requested_by_user_id and total_steps so the UI can say who asked
    and how far through review the request is — an approver needs both to
    judge whether it is theirs to decide.
    """
    steps = (workflow.steps_json if workflow else None) or []
    return {
        "id": i.id,
        "workflow_id": i.workflow_id,
        "workflow_name": workflow.name if workflow else None,
        "action_type": i.action_type,
        "target": i.target,
        "case_id": i.case_id,
        "current_step": i.current_step,
        "total_steps": len(steps) or None,
        "status": i.status,
        "requested_by_user_id": i.requested_by_user_id,
        "approvals": i.approvals_json,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "decided_at": i.decided_at.isoformat() if i.decided_at else None,
    }
