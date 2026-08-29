"""Phase 111: Autonomous Incident Commander - AI IC with voice."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class IncidentCommander(Base):
    __tablename__ = "incident_commanders"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    incident_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    commander_type = Column(String(50), default="ai")  # ai, human, hybrid
    voice_enabled = Column(Boolean, default=True)
    voice_id = Column(String(100), nullable=True)
    status = Column(String(20), default="active")  # active, standby, completed
    created_at = Column(DateTime(timezone=True), default=_now)

class ICDecision(Base):
    __tablename__ = "ic_decisions"
    id = Column(Integer, primary_key=True, index=True)
    commander_id = Column(Integer, ForeignKey("incident_commanders.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    decision_type = Column(String(50), default="contain")  # contain, escalate, delegate, communicate
    title = Column(String(500), nullable=False)
    reasoning_json = Column(JSON, default=dict)  # chain of thought
    confidence = Column(Float, default=0.0)
    delegated_to = Column(String(200), nullable=True)  # agent or human
    status = Column(String(20), default="executed")
    created_at = Column(DateTime(timezone=True), default=_now)

class ICRunbook(Base):
    __tablename__ = "ic_runbooks"
    id = Column(Integer, primary_key=True, index=True)
    commander_id = Column(Integer, ForeignKey("incident_commanders.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    steps_json = Column(JSON, default=list)
    voice_commands_json = Column(JSON, default=list)  # ["isolate host", "notify team"]
    is_autonomous = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)
