"""Phase 71: Continuous compliance + evidence automation."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ComplianceControl(Base):
    __tablename__ = "compliance_controls"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    framework = Column(String(50), nullable=False)  # SOC2, ISO27001, NIST, GDPR
    control_id = Column(String(50), nullable=False)  # CC6.1, A.12.1.1, etc
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Automation: {"evidence_sources": ["audit_logs", "cases"], "check_query": "audit_logs:action=LOGIN"}
    automation_json = Column(JSON, default=dict)
    is_automated = Column(Boolean, default=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    compliance_status = Column(String(20), default="unknown")  # compliant, non_compliant, unknown
    created_at = Column(DateTime(timezone=True), default=_now)

class ComplianceEvidence(Base):
    __tablename__ = "compliance_evidence"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    control_id = Column(Integer, ForeignKey("compliance_controls.id"), nullable=False, index=True)
    evidence_type = Column(String(50), default="audit_log")  # audit_log, case, scan, manual
    # Evidence data
    evidence_json = Column(JSON, default=dict)
    collected_at = Column(DateTime(timezone=True), default=_now)
    is_valid = Column(Boolean, default=True)

class ComplianceAssessment(Base):
    __tablename__ = "compliance_assessments"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    framework = Column(String(50), nullable=False)
    assessment_date = Column(DateTime(timezone=True), default=_now)
    total_controls = Column(Integer, default=0)
    compliant_controls = Column(Integer, default=0)
    compliance_score = Column(Float, default=0.0)  # 0-100
    findings_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
