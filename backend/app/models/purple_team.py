"""Phase 78-79: Purple team simulation."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class PurpleTeamExercise(Base):
    __tablename__ = "purple_team_exercises"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # MITRE ATT&CK
    mitre_tactic = Column(String(50), nullable=True)
    mitre_technique_id = Column(String(20), nullable=True)  # T1059
    # Exercise config
    exercise_type = Column(String(50), default="atomic")  # atomic, chain, full
    steps_json = Column(JSON, default=list)  # [{action: "execute", command: "...", expected_detection: "..."}]
    status = Column(String(20), default="planned")  # planned, running, completed, failed
    # Results
    results_json = Column(JSON, default=dict)  # {detected: bool, alerts_created: [], time_to_detect: ...}
    score = Column(Integer, default=0)  # 0-100 detection score
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class PurpleTeamFinding(Base):
    __tablename__ = "purple_team_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    exercise_id = Column(Integer, ForeignKey("purple_team_exercises.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    finding_type = Column(String(50), default="detection_gap")  # detection_gap, false_positive, improvement
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
