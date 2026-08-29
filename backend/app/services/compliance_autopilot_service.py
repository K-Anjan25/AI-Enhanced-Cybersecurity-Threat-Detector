"""Phase 90: Compliance Autopilot auto-remediate CIS."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.compliance_autopilot import AutopilotRule, AutopilotExecution, AutopilotFinding
from app.models.cspm import CSPMViolation, CloudResource


def _now():
    return datetime.now(timezone.utc)


def create_rule(db: Session, org_id: int, name: str, control_id: str, benchmark: str = "CIS", severity: str = "HIGH", remediation: Dict = None, dry_run: bool = True, require_approval: bool = True, created_by_user_id: int = None) -> AutopilotRule:
    rule = AutopilotRule(org_id=org_id, name=name, control_id=control_id, benchmark=benchmark, severity=severity, remediation_json=remediation or {}, dry_run=dry_run, require_approval=require_approval, created_by_user_id=created_by_user_id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def list_rules(db: Session, org_id: int) -> List[AutopilotRule]:
    return db.query(AutopilotRule).filter(AutopilotRule.org_id == org_id, AutopilotRule.is_active == True).order_by(AutopilotRule.created_at.desc()).all()


def seed_rules(db: Session, org_id: int) -> List[AutopilotRule]:
    existing = db.query(AutopilotRule).filter(AutopilotRule.org_id == org_id).count()
    if existing > 0:
        return list_rules(db, org_id)
    defaults = [
        {"name": "Auto close S3 public access", "control_id": "CIS-2.1", "benchmark": "CIS", "severity": "CRITICAL", "remediation": {"action_type": "close_s3_public", "params": {"block_public_acls": True, "block_public_policy": True}, "approval_required": True, "rollback_action": "open_s3_public"}, "dry_run": True, "require_approval": True},
        {"name": "Auto restrict SG 0.0.0.0/0", "control_id": "CIS-4.1", "benchmark": "CIS", "severity": "HIGH", "remediation": {"action_type": "restrict_sg_ingress", "params": {"remove_cidr": "0.0.0.0/0", "replace_with": "10.0.0.0/24"}, "approval_required": False, "rollback_action": "allow_sg_ingress"}, "dry_run": False, "require_approval": False},
        {"name": "Enable CloudTrail", "control_id": "CIS-3.1", "benchmark": "CIS", "severity": "MEDIUM", "remediation": {"action_type": "enable_cloudtrail", "params": {"multi_region": True}, "approval_required": False}, "dry_run": False, "require_approval": False},
        {"name": "Rotate IAM access keys >90d", "control_id": "CIS-1.4", "benchmark": "CIS", "severity": "MEDIUM", "remediation": {"action_type": "rotate_iam_keys", "params": {"max_age_days": 90}, "approval_required": True}, "dry_run": True, "require_approval": True},
    ]
    created = []
    for d in defaults:
        r = create_rule(db, org_id, d["name"], d["control_id"], d["benchmark"], d["severity"], d["remediation"], d["dry_run"], d["require_approval"])
        created.append(r)
    return created


def evaluate_violations(db: Session, org_id: int) -> List[AutopilotExecution]:
    """Evaluate open CSPM violations against autopilot rules, create executions."""
    violations = db.query(CSPMViolation).filter(CSPMViolation.org_id == org_id, CSPMViolation.status == "open").all()
    rules = list_rules(db, org_id)
    executions = []

    for v in violations:
        # Find matching rule by control_id
        rule = next((r for r in rules if r.control_id == v.control_id and r.benchmark == v.benchmark), None)
        if not rule:
            continue

        # Check if already has execution pending
        existing = db.query(AutopilotExecution).filter(AutopilotExecution.org_id == org_id, AutopilotExecution.violation_id == v.id, AutopilotExecution.status.in_(["pending", "approved"])).first()
        if existing:
            continue

        # Create execution
        exec_status = "pending"
        if rule.dry_run:
            exec_status = "dry_run"

        execution = AutopilotExecution(
            org_id=org_id,
            rule_id=rule.id,
            violation_id=v.id,
            action_type=rule.remediation_json.get("action_type", "remediate"),
            target=f"{v.control_id} on resource {v.resource_id}",
            status=exec_status,
            result_json={"dry_run": rule.dry_run, "violation": {"control_id": v.control_id, "title": v.title, "severity": v.severity}},
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        executions.append(execution)

        # If requires approval and not dry_run, create approval workflow instance
        if rule.require_approval and not rule.dry_run and v.severity in ("CRITICAL", "HIGH"):
            try:
                from app.services import approval_workflow_service
                # Find workflow that matches action
                wfs = approval_workflow_service.list_workflows(db, org_id)
                wf = next((w for w in wfs if "Critical" in w.name), None)
                if wf:
                    inst = approval_workflow_service.request_approval(db, org_id, wf.id, execution.action_type, execution.target, case_id=None, requested_by_user_id=rule.created_by_user_id)
                    execution.approval_instance_id = inst.id
                    db.commit()
            except Exception:
                pass

    return executions


def execute_autopilot(db: Session, org_id: int, execution_id: int, executed_by: str = "autopilot") -> AutopilotExecution:
    """Execute autopilot remediation (mock - in real would call AWS API)."""
    execution = db.query(AutopilotExecution).filter(AutopilotExecution.id == execution_id, AutopilotExecution.org_id == org_id).first()
    if not execution:
        raise ValueError("Execution not found")

    if execution.status not in ("pending", "approved", "dry_run"):
        return execution

    rule = db.query(AutopilotRule).filter(AutopilotRule.id == execution.rule_id).first()
    violation = db.query(CSPMViolation).filter(CSPMViolation.id == execution.violation_id).first() if execution.violation_id else None

    # If requires approval and not approved, block
    if rule and rule.require_approval and execution.status == "pending" and violation and violation.severity in ("CRITICAL", "HIGH"):
        # Check approval instance
        if execution.approval_instance_id:
            from app.models.approval_workflow import ApprovalInstance
            approval = db.query(ApprovalInstance).filter(ApprovalInstance.id == execution.approval_instance_id).first()
            if not approval or approval.status != "approved":
                execution.status = "pending"
                execution.result_json = {"blocked": "Requires approval", "approval_instance_id": execution.approval_instance_id}
                db.commit()
                return execution

    # Mock execution
    if rule and rule.dry_run:
        execution.status = "dry_run"
        execution.result_json = {"dry_run": True, "would_execute": execution.action_type, "target": execution.target, "before": {"public": True}, "after": {"public": False}, "note": "Dry run - no changes made"}
    else:
        execution.status = "executed"
        execution.executed_at = _now()
        execution.executed_by = executed_by
        execution.result_json = {"success": True, "action": execution.action_type, "target": execution.target, "before": {"open": True}, "after": {"open": False}, "rollback_id": f"rollback-{execution.id}"}

        # Mark violation fixed
        if violation:
            violation.status = "fixed"
            db.commit()

        # Increment rule counter
        if rule:
            rule.auto_remediate_count += 1
            db.commit()

        # Create finding
        finding = AutopilotFinding(org_id=org_id, execution_id=execution.id, title=f"Auto-remediated {execution.action_type} on {execution.target}", finding_type="remediation", severity="LOW", description=f"Autopilot executed {execution.action_type} for violation {violation.control_id if violation else 'unknown'}")
        db.add(finding)
        db.commit()

    db.refresh(execution)
    return execution


def list_executions(db: Session, org_id: int, status: str = None) -> List[AutopilotExecution]:
    q = db.query(AutopilotExecution).filter(AutopilotExecution.org_id == org_id)
    if status:
        q = q.filter(AutopilotExecution.status == status)
    return q.order_by(AutopilotExecution.created_at.desc()).limit(100).all()


def get_summary(db: Session, org_id: int) -> Dict[str, Any]:
    total_rules = db.query(AutopilotRule).filter(AutopilotRule.org_id == org_id, AutopilotRule.is_active == True).count()
    total_executions = db.query(AutopilotExecution).filter(AutopilotExecution.org_id == org_id).count()
    executed = db.query(AutopilotExecution).filter(AutopilotExecution.org_id == org_id, AutopilotExecution.status == "executed").count()
    dry_run = db.query(AutopilotExecution).filter(AutopilotExecution.org_id == org_id, AutopilotExecution.status == "dry_run").count()
    pending = db.query(AutopilotExecution).filter(AutopilotExecution.org_id == org_id, AutopilotExecution.status == "pending").count()
    violations = db.query(CSPMViolation).filter(CSPMViolation.org_id == org_id, CSPMViolation.status == "open").count()

    return {"total_rules": total_rules, "total_executions": total_executions, "executed": executed, "dry_run": dry_run, "pending": pending, "open_violations": violations, "auto_remediation_rate": (executed / max(1, total_executions) * 100)}


def serialize_rule(r: AutopilotRule) -> Dict[str, Any]:
    return {"id": r.id, "name": r.name, "control_id": r.control_id, "benchmark": r.benchmark, "severity": r.severity, "remediation": r.remediation_json, "is_active": r.is_active, "dry_run": r.dry_run, "require_approval": r.require_approval, "auto_remediate_count": r.auto_remediate_count, "created_at": r.created_at.isoformat() if r.created_at else None}


def serialize_execution(e: AutopilotExecution) -> Dict[str, Any]:
    return {"id": e.id, "rule_id": e.rule_id, "violation_id": e.violation_id, "action_type": e.action_type, "target": e.target, "status": e.status, "result": e.result_json, "executed_by": e.executed_by, "approval_instance_id": e.approval_instance_id, "created_at": e.created_at.isoformat() if e.created_at else None, "executed_at": e.executed_at.isoformat() if e.executed_at else None}
