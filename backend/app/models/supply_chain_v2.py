"""Phase 107: Supply Chain Defense v2 - deep graph, vendor risk, attestation."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class SupplyChainGraph(Base):
    __tablename__ = "supply_chain_graphs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    root_component = Column(String(300), nullable=True)
    graph_json = Column(JSON, default=dict)  # nodes, edges, depth
    depth = Column(Integer, default=3)
    total_dependencies = Column(Integer, default=0)
    risky_dependencies = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)

class VendorRisk(Base):
    __tablename__ = "vendor_risks"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    vendor_name = Column(String(300), nullable=False)
    risk_score = Column(Float, default=0.0)
    risk_factors = Column(JSON, default=list)
    sbom_compliance = Column(Boolean, default=False)
    attestation_status = Column(String(20), default="pending")
    last_assessed = Column(DateTime(timezone=True), default=_now)
    created_at = Column(DateTime(timezone=True), default=_now)

class Attestation(Base):
    __tablename__ = "attestations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    component_name = Column(String(300), nullable=False)
    attestation_type = Column(String(50), default="slsa")  # slsa, in-toto, sigstore
    predicate_json = Column(JSON, default=dict)
    signature_verified = Column(Boolean, default=False)
    status = Column(String(20), default="verified")
    created_at = Column(DateTime(timezone=True), default=_now)
