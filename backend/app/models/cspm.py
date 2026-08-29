"""Phase 65: CSPM + IaC."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class CloudAccount(Base):
    __tablename__ = "cloud_accounts"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    provider = Column(String(20), nullable=False)  # aws, azure, gcp
    account_id = Column(String(100), nullable=False)
    name = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class CloudResource(Base):
    __tablename__ = "cloud_resources"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("cloud_accounts.id"), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)  # s3_bucket, ec2_instance, iam_policy, etc
    resource_id = Column(String(300), nullable=False)
    name = Column(String(300), nullable=True)
    region = Column(String(50), nullable=True)
    configuration_json = Column(JSON, default=dict)
    risk_score = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class CSPMViolation(Base):
    __tablename__ = "cspm_violations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("cloud_resources.id"), nullable=True, index=True)
    account_id = Column(Integer, ForeignKey("cloud_accounts.id"), nullable=True)
    benchmark = Column(String(50), default="CIS")  # CIS, NIST, SOC2
    control_id = Column(String(50), nullable=False)  # CIS-1.1, etc
    severity = Column(String(20), default="MEDIUM")
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    status = Column(String(20), default="open")  # open, fixed, suppressed
    created_at = Column(DateTime(timezone=True), default=_now)

class IaCScan(Base):
    __tablename__ = "iac_scans"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    scanner = Column(String(50), default="checkov")  # checkov, tfsec, cfn_nag
    target = Column(String(300), nullable=False)  # repo, file path
    status = Column(String(20), default="completed")
    violation_count = Column(Integer, default=0)
    results_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
