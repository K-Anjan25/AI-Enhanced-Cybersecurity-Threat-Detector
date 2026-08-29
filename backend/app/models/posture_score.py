"""Phase 99: Security Posture Score v2 with Business Context."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class PostureScore(Base):
    __tablename__ = "posture_scores"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    # Overall score 0-100
    overall_score = Column(Float, default=0.0)
    # Breakdown
    breakdown_json = Column(JSON, default=dict)  # {detect: 80, protect: 70, respond: 85, etc}
    # Business context: revenue impact, etc
    business_context_json = Column(JSON, default=dict)  # {crown_jewels_protected: 90, compliance: 85}
    # Trends
    previous_score = Column(Float, nullable=True)
    trend = Column(String(20), default="stable")  # improving, degrading, stable
    created_at = Column(DateTime(timezone=True), default=_now)

class PostureFinding(Base):
    __tablename__ = "posture_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    category = Column(String(50), default="protect")  # detect, protect, respond, recover, governance
    title = Column(String(500), nullable=False)
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    impact = Column(String(50), default="medium")  # low, medium, high, critical (business impact)
    remediation = Column(Text, nullable=True)
    # Business context
    business_units = Column(JSON, default=list)
    crown_jewel_affected = Column(Boolean, default=False)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)

class PostureRecommendation(Base):
    __tablename__ = "posture_recommendations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), default="medium")  # low, medium, high, critical
    effort = Column(String(20), default="medium")  # low, medium, high
    impact_score = Column(Float, default=0.0)  # how much score would improve
    # ROI
    estimated_cost = Column(Float, nullable=True)
    estimated_benefit = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
