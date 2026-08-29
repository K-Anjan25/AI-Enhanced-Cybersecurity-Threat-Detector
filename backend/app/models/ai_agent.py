"""Phase 70: AI SOC Agent memory + tool use."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    # Conversation / reasoning trace
    role = Column(String(20), default="user")  # user, assistant, system, tool
    content = Column(Text, nullable=False)
    # Tool use
    tool_name = Column(String(100), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    # Metadata
    step = Column(Integer, default=0)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    task_type = Column(String(50), default="investigate")  # investigate, hunt, vuln_correlate, ztna_evaluate
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    steps_taken = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
