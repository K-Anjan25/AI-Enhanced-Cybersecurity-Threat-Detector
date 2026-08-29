"""Phase 115: Autonomous Compliance Auditor v2."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ComplianceAuditV2(Base):
    __tablename__ = "compliance_audits_v2"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    framework = Column(String(50), default="SOC2")  # SOC2, ISO27001, NIST, GDPR, FedRAMP
    auditor_type = Column(String(50), default="llm")  # llm, hybrid, human
    scope_json = Column(JSON, default=dict)  # controls in scope
    status = Column(String(20), default="running")  # running, completed, failed
    compliance_score = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class AuditFindingV2(Base):
    __tablename__ = "audit_findings_v2"
    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(Integer, ForeignKey("compliance_audits_v2.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    control_id = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    severity = Column(String(20), default="MEDIUM")
    status = Column(String(20), default="open")  # open, remediated, exception
    llm_reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class AuditEvidenceV2(Base):
    __tablename__ = "audit_evidence_v2"
    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("audit_findings_v2.id"), nullable=True)
    audit_id = Column(Integer, ForeignKey("compliance_audits_v2.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    evidence_type = Column(String(50), default="log")  # log, config, screenshot, attestation
    evidence_json = Column(JSON, default=dict)
    collected_by = Column(String(50), default="llm")
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
