"""Phase 98: Cloud-Native Application Protection Platform (CNAPP)."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class CNAPP_Cluster(Base):
    __tablename__ = "cnapp_clusters"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    cluster_type = Column(String(50), default="kubernetes")  # kubernetes, ecs, etc
    provider = Column(String(20), default="aws")  # aws, azure, gcp
    region = Column(String(50), nullable=True)
    version = Column(String(50), nullable=True)
    node_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class CNAPP_Workload(Base):
    __tablename__ = "cnapp_workloads"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    cluster_id = Column(Integer, ForeignKey("cnapp_clusters.id"), nullable=False)
    name = Column(String(300), nullable=False)
    namespace = Column(String(100), default="default")
    workload_type = Column(String(50), default="deployment")  # deployment, pod, daemonset
    image = Column(String(500), nullable=True)
    # Security
    is_privileged = Column(Boolean, default=False)
    has_host_network = Column(Boolean, default=False)
    vulnerabilities = Column(JSON, default=list)  # list of CVEs
    compliance_violations = Column(JSON, default=list)
    risk_score = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class CNAPP_Policy(Base):
    __tablename__ = "cnapp_policies"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    policy_type = Column(String(50), default="psp")  # psp, network_policy, admission_controller
    # Policy definition
    policy_json = Column(JSON, default=dict)
    severity = Column(String(20), default="MEDIUM")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class CNAPP_Finding(Base):
    __tablename__ = "cnapp_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    cluster_id = Column(Integer, ForeignKey("cnapp_clusters.id"), nullable=True)
    workload_id = Column(Integer, ForeignKey("cnapp_workloads.id"), nullable=True)
    title = Column(String(500), nullable=False)
    finding_type = Column(String(100), default="vulnerability")
    severity = Column(String(20), default="HIGH")
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
