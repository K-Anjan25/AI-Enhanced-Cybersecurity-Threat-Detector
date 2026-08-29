"""Phase 85: SOAR Approval Workflows."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Workflow definition: steps with approvers, conditions
    # e.g. [{step: 1, name: "SOC Lead", approver_roles: ["admin"], approver_users: [], action_types: ["block_ip", "isolate_host"], min_approvals: 1}]
    steps_json = Column(JSON, default=list)
    # Trigger conditions: {severity: ["HIGH", "CRITICAL"], action_types: ["block_ip"]}
    trigger_json = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class ApprovalInstance(Base):
    __tablename__ = "approval_instances"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey("approval_workflows.id"), nullable=False, index=True)
    # What needs approval
    soar_action_id = Column(Integer, ForeignKey("soar_actions.id"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    action_type = Column(String(100), nullable=True)
    target = Column(String(500), nullable=True)
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Current step
    current_step = Column(Integer, default=1)
    status = Column(String(20), default="pending")  # pending, approved, rejected, expired
    # Approvals collected
    approvals_json = Column(JSON, default=list)  # [{user_id, decision, comment, at}]
    created_at = Column(DateTime(timezone=True), default=_now)
    decided_at = Column(DateTime(timezone=True), nullable=True)

class ApprovalTask(Base):
    __tablename__ = "approval_tasks"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    instance_id = Column(Integer, ForeignKey("approval_instances.id"), nullable=False, index=True)
    step = Column(Integer, default=1)
    assignee_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assignee_role = Column(String(50), nullable=True)  # admin, analyst
    status = Column(String(20), default="pending")  # pending, approved, rejected
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
