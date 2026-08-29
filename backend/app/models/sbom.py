"""Phase 66: Supply Chain SBOM."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class SBOM(Base):
    __tablename__ = "sboms"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    version = Column(String(50), nullable=True)
    format = Column(String(20), default="cyclonedx")  # cyclonedx, spdx
    source = Column(String(300), nullable=True)  # image, repo, file
    component_count = Column(Integer, default=0)
    vuln_count = Column(Integer, default=0)
    sbom_json = Column(JSON, default=dict)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class Dependency(Base):
    __tablename__ = "sbom_dependencies"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    sbom_id = Column(Integer, ForeignKey("sboms.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    version = Column(String(100), nullable=True)
    purl = Column(String(500), nullable=True)  # package url
    license = Column(String(100), nullable=True)
    risk_score = Column(Float, default=0.0)
    vuln_count = Column(Integer, default=0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class SupplyChainRisk(Base):
    __tablename__ = "supply_chain_risks"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    dependency_id = Column(Integer, ForeignKey("sbom_dependencies.id"), nullable=True)
    sbom_id = Column(Integer, ForeignKey("sboms.id"), nullable=True)
    risk_type = Column(String(50), nullable=False)  # vulnerable_dependency, malicious_package, outdated, license_risk
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    cve_id = Column(String(30), nullable=True)
    cvss_score = Column(Float, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
