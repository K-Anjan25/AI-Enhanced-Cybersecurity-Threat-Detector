"""Phase 62: Threat hunting workbench."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class Hunt(Base):
    __tablename__ = "hunts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # KQL/Lucene query: e.g. 'severity:CRITICAL AND source_ip:10.0.0.1'
    query = Column(Text, nullable=False)
    query_language = Column(String(20), default="kql")  # kql, lucene, sigma
    # Optional Sigma rule reference
    sigma_rule_id = Column(Integer, ForeignKey("sigma_rules.id"), nullable=True)
    is_saved = Column(Boolean, default=False)
    is_scheduled = Column(Boolean, default=False)
    schedule_cron = Column(String(100), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class HuntExecution(Base):
    __tablename__ = "hunt_executions"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    hunt_id = Column(Integer, ForeignKey("hunts.id"), nullable=False, index=True)
    query = Column(Text, nullable=False)
    status = Column(String(20), default="completed")  # running, completed, failed
    result_count = Column(Integer, default=0)
    results_json = Column(JSON, nullable=True)  # top results
    error = Column(Text, nullable=True)
    executed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    executed_at = Column(DateTime(timezone=True), default=_now)
    duration_ms = Column(Integer, nullable=True)
