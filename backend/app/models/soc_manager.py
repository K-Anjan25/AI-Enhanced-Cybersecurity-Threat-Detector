"""Phase 96: AI SOC Manager - multi-agent orchestration."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class SOCManagerDashboard(Base):
    __tablename__ = "soc_manager_dashboards"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # Agents: list of active agents with status
    agents_json = Column(JSON, default=list)  # [{name, role, status, current_case_id, metrics}]
    # Orchestration policy
    policy_json = Column(JSON, default=dict)  # {auto_assign: true, max_cases_per_agent: 5}
    created_at = Column(DateTime(timezone=True), default=_now)

class AgentOrchestration(Base):
    __tablename__ = "agent_orchestrations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    # Orchestration: which agents assigned, workflow
    workflow_json = Column(JSON, default=list)  # [{agent, task, status, order}]
    status = Column(String(20), default="running")  # running, completed, failed
    # Result: consensus, final action
    result_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class AgentPerformance(Base):
    __tablename__ = "agent_performance"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    # Metrics
    cases_handled = Column(Integer, default=0)
    avg_time_to_triage = Column(Float, default=0.0)  # minutes
    accuracy = Column(Float, default=0.0)  # 0-100
    false_positive_rate = Column(Float, default=0.0)
    recorded_at = Column(DateTime(timezone=True), default=_now)
