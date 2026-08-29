"""Phase 90: Compliance Autopilot auto-remediate CIS."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AutopilotRule(Base):
    __tablename__ = "autopilot_rules"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Trigger: benchmark CIS, control_id, severity
    benchmark = Column(String(50), default="CIS")  # CIS, NIST, SOC2
    control_id = Column(String(50), nullable=False)  # CIS-2.1, CIS-4.1, etc
    severity = Column(String(20), default="HIGH")
    # Auto-remediation action: {action_type, params, approval_required}
    # e.g. {action_type: "close_s3_public", params: {bucket: "{{resource.name}}"}, approval_required: True}
    remediation_json = Column(JSON, default=dict)
    # Safety: dry_run, max_auto_remediate_per_day, require_approval_for_critical
    is_active = Column(Boolean, default=True)
    dry_run = Column(Boolean, default=True)  # if True, only log, don't execute
    require_approval = Column(Boolean, default=True)  # if True, needs approval workflow for CRITICAL
    auto_remediate_count = Column(Integer, default=0)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class AutopilotExecution(Base):
    __tablename__ = "autopilot_executions"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("autopilot_rules.id"), nullable=False, index=True)
    violation_id = Column(Integer, ForeignKey("cspm_violations.id"), nullable=True)
    # Execution details
    action_type = Column(String(100), nullable=False)
    target = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, executed, failed, dry_run
    # Result
    result_json = Column(JSON, default=dict)  # {success, before, after, rollback_id}
    executed_by = Column(String(50), default="autopilot")  # autopilot, user, approval_workflow
    approval_instance_id = Column(Integer, ForeignKey("approval_instances.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    executed_at = Column(DateTime(timezone=True), nullable=True)

class AutopilotFinding(Base):
    __tablename__ = "autopilot_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    execution_id = Column(Integer, ForeignKey("autopilot_executions.id"), nullable=True)
    title = Column(String(500), nullable=False)
    finding_type = Column(String(100), default="remediation")
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
