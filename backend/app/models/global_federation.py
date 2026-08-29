"""Phase 101: Global SOC Federation - multi-tenant global SOC as a service."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class GlobalFederation(Base):
    __tablename__ = "global_federations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # Federation config: regions, data residency, compliance
    regions_json = Column(JSON, default=list)  # ["us-east-1","eu-west-1","ap-south-1"]
    data_residency_json = Column(JSON, default=dict)  # {"EU": "eu-only", "US": "us-only"}
    compliance_frameworks = Column(JSON, default=list)  # ["GDPR","CCPA","FedRAMP"]
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class FederatedTenant(Base):
    __tablename__ = "federated_tenants"
    id = Column(Integer, primary_key=True, index=True)
    federation_id = Column(Integer, ForeignKey("global_federations.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    tenant_name = Column(String(300), nullable=False)
    region = Column(String(50), default="us-east-1")
    trust_score = Column(Float, default=80.0)
    data_sharing_level = Column(String(20), default="anonymized")  # none, anonymized, full
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class CrossBorderCaseShare(Base):
    __tablename__ = "cross_border_case_shares"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    federation_id = Column(Integer, ForeignKey("global_federations.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    shared_with_orgs = Column(JSON, default=list)
    anonymization_level = Column(String(20), default="pii_stripped")
    tlp = Column(String(20), default="AMBER")
    status = Column(String(20), default="shared")
    created_at = Column(DateTime(timezone=True), default=_now)
