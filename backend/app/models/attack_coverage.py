"""Phase 82: ATT&CK Coverage Dashboard."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AttackCoverage(Base):
    __tablename__ = "attack_coverage"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    mitre_tactic = Column(String(50), nullable=False)  # initial-access, execution, etc
    mitre_technique_id = Column(String(20), nullable=False)  # T1059
    mitre_technique_name = Column(String(200), nullable=True)
    # Coverage
    has_detection_rule = Column(Boolean, default=False)
    has_hunt = Column(Boolean, default=False)
    has_playbook = Column(Boolean, default=False)
    has_purple_exercise = Column(Boolean, default=False)
    detection_count = Column(Integer, default=0)  # how many alerts mapped
    coverage_score = Column(Float, default=0.0)  # 0-100
    # Gap analysis
    gap_reason = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    last_evaluated_at = Column(DateTime(timezone=True), default=_now)
    created_at = Column(DateTime(timezone=True), default=_now)

class AttackCoverageReport(Base):
    __tablename__ = "attack_coverage_reports"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    total_techniques = Column(Integer, default=0)
    covered_techniques = Column(Integer, default=0)
    coverage_percent = Column(Float, default=0.0)
    # Breakdown by tactic
    tactic_breakdown_json = Column(JSON, default=dict)  # {tactic: {total, covered, percent}}
    gaps_json = Column(JSON, default=list)  # list of uncovered techniques
    created_at = Column(DateTime(timezone=True), default=_now)
